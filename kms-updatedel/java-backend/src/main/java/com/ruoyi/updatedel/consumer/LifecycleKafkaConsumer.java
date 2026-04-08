package com.ruoyi.updatedel.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.KeyPayload;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.SysUser;
import com.ruoyi.updatedel.repository.KeymanageRepository;
import com.ruoyi.updatedel.repository.SysUserRepository;
import com.ruoyi.updatedel.service.LifecycleService;
import java.io.IOException;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class LifecycleKafkaConsumer {
    private static final Logger log = LoggerFactory.getLogger(LifecycleKafkaConsumer.class);

    private final ObjectMapper objectMapper;
    private final SysUserRepository sysUserRepository;
    private final KeymanageRepository keymanageRepository;
    private final LifecycleService lifecycleService;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public LifecycleKafkaConsumer(ObjectMapper objectMapper,
                                  SysUserRepository sysUserRepository,
                                  KeymanageRepository keymanageRepository,
                                  LifecycleService lifecycleService) {
        this.objectMapper = objectMapper;
        this.sysUserRepository = sysUserRepository;
        this.keymanageRepository = keymanageRepository;
        this.lifecycleService = lifecycleService;
    }

    @KafkaListener(topics = "${kms.lifecycle.kafka.update-topic:key_update_log}", groupId = "${spring.kafka.consumer.group-id}")
    public void consumeUpdate(String payloadText) {
        handle(payloadText, true);
    }

    @KafkaListener(topics = "${kms.lifecycle.kafka.revoke-topic:key_revoke_log}", groupId = "${spring.kafka.consumer.group-id}")
    public void consumeRevoke(String payloadText) {
        handle(payloadText, false);
    }

    private void handle(String payloadText, boolean rotate) {
        try {
            KeyPayload payload = objectMapper.readValue(payloadText, KeyPayload.class);
            if (!isAuthorized(payload)) {
                log.warn("lifecycle kafka auth failed, user={}, keyId={}, traceId={}", payload.getRawUser(), payload.getKeyId(), payload.getTraceId());
                return;
            }

            Optional<Keymanage> keyOptional = keymanageRepository.findById(payload.getKeyId());
            if (!keyOptional.isPresent()) {
                log.warn("lifecycle kafka key not found, keyId={}, traceId={}", payload.getKeyId(), payload.getTraceId());
                return;
            }

            Keymanage current = keyOptional.get();
            if (!current.getUserName().equals(payload.getRawUser())) {
                log.warn("lifecycle kafka key owner mismatch, keyId={}, traceId={}", payload.getKeyId(), payload.getTraceId());
                return;
            }

            if (rotate) {
                if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
                    log.warn("revoked key cannot rotate, keyId={}, traceId={}", payload.getKeyId(), payload.getTraceId());
                    return;
                }
                Keymanage request = payload.getKeyInfo() == null ? new Keymanage() : payload.getKeyInfo();
                request.setKeyId(payload.getKeyId());
                lifecycleService.rotateKey(request);
                log.info("UPDATE_KEY consumed successfully, keyId={}, traceId={}", payload.getKeyId(), payload.getTraceId());
            } else {
                lifecycleService.revokeKey(payload.getKeyId());
                log.info("REVOKE_KEY consumed successfully, keyId={}, traceId={}", payload.getKeyId(), payload.getTraceId());
            }
        } catch (IOException ex) {
            log.error("lifecycle kafka payload parse error", ex);
        } catch (Exception ex) {
            log.error("lifecycle kafka process error", ex);
        }
    }

    private boolean isAuthorized(KeyPayload payload) {
        if (payload.getRawUser() == null || payload.getRawPassword() == null) {
            return false;
        }
        Optional<SysUser> userOptional = sysUserRepository.findByUserName(payload.getRawUser());
        if (!userOptional.isPresent()) {
            return false;
        }
        String encodedPassword = userOptional.get().getPassword();
        return encodedPassword != null && passwordEncoder.matches(payload.getRawPassword(), encodedPassword);
    }
}
