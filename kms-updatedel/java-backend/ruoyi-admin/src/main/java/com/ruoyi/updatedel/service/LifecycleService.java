package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.service.generator.EccKeyGenerator;
import com.ruoyi.updatedel.service.generator.SsclKeyGenerator;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LifecycleService {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final KeymanageMapper keymanageMapper;
    private final EccKeyGenerator eccKeyGenerator;
    private final SsclKeyGenerator ssclKeyGenerator;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;

    @Value("${kms.lifecycle.kafka.chain-task-topic:key_chain_task}")
    private String chainTaskTopic;

    public LifecycleService(
        KeymanageMapper keymanageMapper,
        EccKeyGenerator eccKeyGenerator,
        SsclKeyGenerator ssclKeyGenerator,
        KafkaTemplate<String, String> kafkaTemplate,
        ObjectMapper objectMapper
    ) {
        this.keymanageMapper = keymanageMapper;
        this.eccKeyGenerator = eccKeyGenerator;
        this.ssclKeyGenerator = ssclKeyGenerator;
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
    }

    public List<Keymanage> list(Keymanage query) {
        return keymanageMapper.selectkeymanageList(query);
    }

    public Optional<Keymanage> findById(Long keyId) {
        return Optional.ofNullable(keymanageMapper.selectkeymanageByKeyId(keyId));
    }

    @Transactional
    public Keymanage rotateKey(Keymanage request) {
        Keymanage current = requireExistingKey(request.getKeyId());
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            throw new IllegalStateException("该密钥已被回收，无法更新");
        }

        Keymanage next = mergeForRotation(current, request);
        next.setVersion(current.getVersion() == null ? 2 : current.getVersion() + 1);
        next.setStatus(KeyStatus.ACTIVE.getCode());
        next.setChainStatus("0");
        next.setUpdTime(now());
        next.setKeyValue(generateKeyValue(next));

        keymanageMapper.updatekeymanage(next);
        publishChainEvent(ChainSyncEvent.TYPE_ROTATE, next);
        return requireExistingKey(next.getKeyId());
    }

    @Transactional
    public void revokeKey(Long keyId) {
        Keymanage current = requireExistingKey(keyId);
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            return;
        }
        keymanageMapper.revoke(keyId, KeyStatus.REVOKED.getCode());
        Keymanage revoked = requireExistingKey(keyId);
        publishChainEvent(ChainSyncEvent.TYPE_REVOKE, revoked);
    }

    public void updateAutoUpdate(Long keyId, String autoUpdate) {
        Keymanage current = requireExistingKey(keyId);
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            throw new IllegalStateException("该密钥已被回收，无法修改自动更新状态");
        }
        keymanageMapper.updateAutoUpdate(keyId, normalizeAutoUpdate(autoUpdate));
    }

    private Keymanage requireExistingKey(Long keyId) {
        return Optional.ofNullable(keymanageMapper.selectkeymanageByKeyId(keyId))
            .orElseThrow(() -> new IllegalStateException("密钥不存在: " + keyId));
    }

    private Keymanage mergeForRotation(Keymanage current, Keymanage request) {
        Keymanage merged = new Keymanage();
        merged.setKeyId(current.getKeyId());
        merged.setUserId(current.getUserId());
        merged.setUserName(valueOrDefault(request.getUserName(), current.getUserName()));
        merged.setUa(valueOrDefault(request.getUa(), current.getUa()));
        merged.setEncrytType(valueOrDefault(request.getEncrytType(), current.getEncrytType()));
        merged.setEncrytName(valueOrDefault(request.getEncrytName(), current.getEncrytName()));
        merged.setKeyName(valueOrDefault(request.getKeyName(), current.getKeyName()));
        merged.setKeyUse(valueOrDefault(request.getKeyUse(), current.getKeyUse()));
        merged.setKeyValue(current.getKeyValue());
        merged.setCreTime(current.getCreTime());
        merged.setAutoUpdate(normalizeAutoUpdate(valueOrDefault(request.getAutoUpdate(), current.getAutoUpdate())));
        merged.setKeyDomain(valueOrDefault(request.getKeyDomain(), current.getKeyDomain()));
        return merged;
    }

    private String generateKeyValue(Keymanage key) {
        if ("对称加密".equals(key.getEncrytType()) && "AES".equalsIgnoreCase(key.getEncrytName())) {
            return generateAesKey();
        }
        if ("无证书非对称加密".equals(key.getEncrytType()) && "SM2".equalsIgnoreCase(key.getEncrytName())) {
            return eccKeyGenerator.generate(key.getUserName(), key.getUa());
        }
        if ("无证书非对称加密".equals(key.getEncrytType()) && "SSCL".equalsIgnoreCase(key.getEncrytName())) {
            return ssclKeyGenerator.generate(key.getUserName(), key.getUa(), key.getKeyDomain());
        }
        return key.getKeyValue();
    }

    private String generateAesKey() {
        try {
            KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
            keyGenerator.init(256);
            SecretKey secretKey = keyGenerator.generateKey();
            byte[] bytes = secretKey.getEncoded();
            StringBuilder builder = new StringBuilder();
            for (byte current : bytes) {
                builder.append(String.format("%02x", current));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("AES 密钥生成失败", ex);
        }
    }

    private void publishChainEvent(String actionType, Keymanage keymanage) {
        try {
            kafkaTemplate.send(chainTaskTopic, objectMapper.writeValueAsString(new ChainSyncEvent(actionType, Collections.singletonList(keymanage))));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("上链任务序列化失败", ex);
        }
    }

    private String normalizeAutoUpdate(String autoUpdate) {
        if (autoUpdate == null || autoUpdate.trim().isEmpty()) {
            return "0";
        }
        String value = autoUpdate.trim();
        if ("true".equalsIgnoreCase(value) || "enabled".equalsIgnoreCase(value)) {
            return "1";
        }
        if ("false".equalsIgnoreCase(value) || "disabled".equalsIgnoreCase(value)) {
            return "0";
        }
        return value;
    }

    private String valueOrDefault(String candidate, String fallback) {
        return candidate == null || candidate.trim().isEmpty() ? fallback : candidate;
    }

    private String now() {
        return LocalDateTime.now().format(FORMATTER);
    }
}
