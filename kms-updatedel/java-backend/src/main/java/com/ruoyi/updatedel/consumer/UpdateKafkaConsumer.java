package com.ruoyi.updatedel.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.common.AjaxResult;
import com.ruoyi.updatedel.domain.KeyPayload;
import com.ruoyi.updatedel.domain.SysUser;
import com.ruoyi.updatedel.repository.SysUserRepository;
import com.ruoyi.updatedel.service.KeyRotateService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.Optional;

/**
 * 密钥轮换 Kafka 消费者
 * 消费 key_update_log topic，处理 UPDATE_KEY 类型消息
 */
@Component
public class UpdateKafkaConsumer {
    private static final Logger log = LoggerFactory.getLogger(UpdateKafkaConsumer.class);

    private final ObjectMapper objectMapper;
    private final SysUserRepository sysUserRepository;
    private final KeyRotateService keyRotateService;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public UpdateKafkaConsumer(
            ObjectMapper objectMapper,
            SysUserRepository sysUserRepository,
            KeyRotateService keyRotateService) {
        this.objectMapper = objectMapper;
        this.sysUserRepository = sysUserRepository;
        this.keyRotateService = keyRotateService;
    }

    @KafkaListener(
            topics = "${kms.lifecycle.kafka.update-topic:key_update_log}",
            groupId = "kms-updatedel-consumer-group"
    )
    public void onMessage(String payloadText) {
        long startTime = System.currentTimeMillis();

        try {
            KeyPayload payload = objectMapper.readValue(payloadText, KeyPayload.class);
            if (!isAuthorized(payload)) {
                log.warn("UpdateKafkaConsumer auth failed, user={}, keyId={}, traceId={}",
                        payload.getRawUser(), payload.getKeyId(), payload.getTraceId());
                return;
            }

            Long keyId = payload.getKeyId();
            if (keyId == null || keyId <= 0) {
                log.warn("UpdateKafkaConsumer missing keyId, traceId={}", payload.getTraceId());
                return;
            }

            // 调用轮换服务
            AjaxResult result = keyRotateService.rotateKeyById(keyId);
            long cost = System.currentTimeMillis() - startTime;

            if (AjaxResult.SUCCESS_CODE == (Integer) result.get("code")) {
                log.info("UPDATE_KEY consumed successfully, keyId={}, traceId={}, cost={}ms",
                        keyId, payload.getTraceId(), cost);
            } else {
                log.warn("UPDATE_KEY consume failed, keyId={}, traceId={}, msg={}",
                        keyId, payload.getTraceId(), result.get("msg"));
            }

        } catch (Exception ex) {
            log.error("UpdateKafkaConsumer process error, traceId={}", payloadText, ex);
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
