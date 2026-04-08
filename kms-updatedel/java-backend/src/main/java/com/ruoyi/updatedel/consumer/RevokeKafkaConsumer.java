package com.ruoyi.updatedel.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.common.AjaxResult;
import com.ruoyi.updatedel.domain.KeyPayload;
import com.ruoyi.updatedel.domain.SysUser;
import com.ruoyi.updatedel.repository.SysUserRepository;
import com.ruoyi.updatedel.service.KeyRevokeService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.Optional;

/**
 * 密钥回收 Kafka 消费者
 * 消费 key_revoke_log topic，处理 REVOKE_KEY 类型消息
 */
@Component
public class RevokeKafkaConsumer {
    private static final Logger log = LoggerFactory.getLogger(RevokeKafkaConsumer.class);

    private final ObjectMapper objectMapper;
    private final SysUserRepository sysUserRepository;
    private final KeyRevokeService keyRevokeService;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public RevokeKafkaConsumer(
            ObjectMapper objectMapper,
            SysUserRepository sysUserRepository,
            KeyRevokeService keyRevokeService) {
        this.objectMapper = objectMapper;
        this.sysUserRepository = sysUserRepository;
        this.keyRevokeService = keyRevokeService;
    }

    @KafkaListener(
            topics = "${kms.lifecycle.kafka.revoke-topic:key_revoke_log}",
            groupId = "kms-updatedel-consumer-group"
    )
    public void onMessage(String payloadText) {
        long startTime = System.currentTimeMillis();

        try {
            KeyPayload payload = objectMapper.readValue(payloadText, KeyPayload.class);
            if (!isAuthorized(payload)) {
                log.warn("RevokeKafkaConsumer auth failed, user={}, keyId={}, traceId={}",
                        payload.getRawUser(), payload.getKeyId(), payload.getTraceId());
                return;
            }

            Long keyId = payload.getKeyId();
            if (keyId == null || keyId <= 0) {
                log.warn("RevokeKafkaConsumer missing keyId, traceId={}", payload.getTraceId());
                return;
            }

            // 调用回收服务
            AjaxResult result = keyRevokeService.revokeKeyById(keyId);
            long cost = System.currentTimeMillis() - startTime;

            if (AjaxResult.SUCCESS_CODE.equals(result.get("code"))) {
                log.info("REVOKE_KEY consumed successfully, keyId={}, traceId={}, cost={}ms",
                        keyId, payload.getTraceId(), cost);
            } else {
                log.warn("REVOKE_KEY consume failed, keyId={}, traceId={}, msg={}",
                        keyId, payload.getTraceId(), result.get("msg"));
            }

        } catch (Exception ex) {
            log.error("RevokeKafkaConsumer process error, payload={}", payloadText, ex);
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