package com.ruoyi.updatedel.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.KeyPayload;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.mapper.SysUserMapper;
import com.ruoyi.updatedel.service.LifecycleService;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class LifecycleKafkaConsumer {
    private static final Logger log = LoggerFactory.getLogger(LifecycleKafkaConsumer.class);

    private final ObjectMapper objectMapper;
    private final SysUserMapper sysUserMapper;
    private final KeymanageMapper keymanageMapper;
    private final LifecycleService lifecycleService;

    public LifecycleKafkaConsumer(ObjectMapper objectMapper,
                                  SysUserMapper sysUserMapper,
                                  KeymanageMapper keymanageMapper,
                                  LifecycleService lifecycleService) {
        this.objectMapper = objectMapper;
        this.sysUserMapper = sysUserMapper;
        this.keymanageMapper = keymanageMapper;
        this.lifecycleService = lifecycleService;
    }

    @KafkaListener(
        topics = "${kms.lifecycle.kafka.update-topic:key_update_log}",
        groupId = "${spring.kafka.consumer.group-id}",
        concurrency = "${kms.lifecycle.kafka.consumer-concurrency:6}",
        properties = {
            "fetch.min.bytes=${kms.lifecycle.kafka.update-fetch-min-bytes:65536}",
            "fetch.max.wait.ms=${kms.lifecycle.kafka.update-fetch-max-wait-ms:20}"
        }
    )
    public void consumeUpdate(List<ConsumerRecord<String, String>> records) {
        Map<String, List<Keymanage>> byUser = new LinkedHashMap<>();
        Map<String, Boolean> authCache = new LinkedHashMap<>();
        for (ConsumerRecord<String, String> record : records) {
            if (record == null || record.value() == null || record.value().trim().isEmpty()) {
                continue;
            }
            try {
                KeyPayload payload = objectMapper.readValue(record.value(), KeyPayload.class);
                if (payload.getKeyId() == null || !isAuthorized(payload, authCache)) {
                    continue;
                }
                Keymanage request = payload.getKeyInfo() == null ? new Keymanage() : payload.getKeyInfo();
                request.setKeyId(payload.getKeyId());
                applyProofContext(payload, request);
                byUser.computeIfAbsent(payload.getRawUser(), ignored -> new ArrayList<>()).add(request);
            } catch (IOException ex) {
                log.warn("update payload rejected, offset={}", record.offset());
            }
        }
        for (Map.Entry<String, List<Keymanage>> entry : byUser.entrySet()) {
            List<Keymanage> requests = entry.getValue();
            for (int start = 0; start < requests.size(); start += 500) {
                List<Keymanage> batch = new ArrayList<>(requests.subList(start, Math.min(start + 500, requests.size())));
                try {
                    lifecycleService.rotateKeys(entry.getKey(), batch);
                } catch (Exception ex) {
                    // The batch rolled back. Isolate invalid keys without losing valid siblings.
                    for (Keymanage request : batch) {
                        try {
                            lifecycleService.rotateKeys(entry.getKey(), java.util.Collections.singletonList(request));
                        } catch (Exception failure) {
                            log.warn("update rejected, keyId={}, failure={}", request.getKeyId(), failure.getClass().getSimpleName());
                        }
                    }
                }
            }
        }
    }

    @KafkaListener(
        topics = "${kms.lifecycle.kafka.revoke-topic:key_revoke_log}",
        groupId = "${spring.kafka.consumer.group-id}",
        concurrency = "${kms.lifecycle.kafka.consumer-concurrency:6}"
    )
    public void consumeRevoke(List<ConsumerRecord<String, String>> records) {
        handleRevokeBatch(records);
    }

    private void handleRevokeBatch(List<ConsumerRecord<String, String>> records) {
        Map<String, Set<Long>> keyIdsByUser = new LinkedHashMap<>();
        Map<String, Boolean> authCache = new LinkedHashMap<>();
        int payloadCount = 0;
        int skippedCount = 0;

        for (ConsumerRecord<String, String> record : records) {
            if (record == null || record.value() == null || record.value().trim().isEmpty()) {
                skippedCount++;
                continue;
            }
            try {
                KeyPayload payload = objectMapper.readValue(record.value(), KeyPayload.class);
                payloadCount++;
                if (payload.getKeyId() == null || !isAuthorized(payload, authCache)) {
                    skippedCount++;
                    continue;
                }
                // 归属校验：消息声明的用户必须确实是该密钥的所有者，
                // 否则可借批量回收接口跨用户回收他人密钥。
                Keymanage owner = keymanageMapper.selectkeymanageByKeyId(payload.getKeyId());
                if (owner == null) {
                    skippedCount++;
                    log.warn("lifecycle kafka revoke key not found, keyId={}, traceId={}",
                        payload.getKeyId(), payload.getTraceId());
                    continue;
                }
                if (!payload.getRawUser().equals(owner.getUserName())) {
                    skippedCount++;
                    log.warn("lifecycle kafka revoke owner mismatch, keyId={}, declaredUser={}, traceId={}",
                        payload.getKeyId(), payload.getRawUser(), payload.getTraceId());
                    continue;
                }
                keyIdsByUser.computeIfAbsent(payload.getRawUser(), ignored -> new LinkedHashSet<>())
                    .add(payload.getKeyId());
            } catch (IOException ex) {
                skippedCount++;
                log.warn("lifecycle kafka revoke payload parse error, offset={}", record.offset(), ex);
            } catch (Exception ex) {
                skippedCount++;
                log.warn("lifecycle kafka revoke payload pre-process error, offset={}", record.offset(), ex);
            }
        }

        int affectedCount = 0;
        for (Map.Entry<String, Set<Long>> entry : keyIdsByUser.entrySet()) {
            affectedCount += lifecycleService.revokeKeys(entry.getKey(), new ArrayList<>(entry.getValue()));
        }
        log.info("REVOKE_KEY batch consumed, records={}, payloads={}, users={}, affected={}, skipped={}",
            records.size(), payloadCount, keyIdsByUser.size(), affectedCount, skippedCount);
    }

    /**
     * 校验消息声明的用户确实存在。
     * <p>
     * 安全边界已上移到 Go 入站层（身份经 X-Kms-User 内部头由 Java 业务层传递，
     * Go 不再信任请求体中的 user，且入站路由不对外暴露）。
     * 此处不再以「密码为空」作为可信判据——那正是先前的鉴权绕过点。
     * 密钥归属（key.user_name == payload.raw_user）由 handle / handleRevokeBatch 单独校验。
     */
    private boolean isAuthorized(KeyPayload payload) {
        if (payload.getRawUser() == null || payload.getRawUser().trim().isEmpty()) {
            return false;
        }
        if (payload.getRawPassword() != null && !payload.getRawPassword().trim().isEmpty()) {
            log.warn("收到携带明文密码的生命周期消息（旧调用方），已忽略该字段: user={}", payload.getRawUser());
        }
        return sysUserMapper.selectUserByUserName(payload.getRawUser()) != null;
    }

    private boolean isAuthorized(KeyPayload payload, Map<String, Boolean> authCache) {
        if (payload.getRawUser() == null || payload.getRawUser().trim().isEmpty()) {
            return false;
        }
        String rawPassword = payload.getRawPassword() == null ? "" : payload.getRawPassword();
        String cacheKey = payload.getRawUser() + "\n" + rawPassword;
        Boolean cached = authCache.get(cacheKey);
        if (cached != null) {
            return cached;
        }
        boolean authorized = isAuthorized(payload);
        authCache.put(cacheKey, authorized);
        return authorized;
    }

    private void applyProofContext(KeyPayload payload, Keymanage request) {
        request.setBatchId(payload.getBatchId());
        request.setParentBatchId(payload.getParentBatchId());
        request.setRootBatchId(payload.getRootBatchId());
        request.setTreePath(payload.getTreePath());
        request.setTreeLevel(payload.getTreeLevel());
        request.setNodeIndex(payload.getNodeIndex());
        request.setExpectedCount(payload.getExpectedCount());
        request.setTreeFanout(payload.getTreeFanout());
        request.setProofMode(payload.getProofMode());
        request.setCommitmentSeed(payload.getCommitmentSeed());
    }
}
