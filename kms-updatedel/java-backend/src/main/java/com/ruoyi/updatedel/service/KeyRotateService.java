package com.ruoyi.updatedel.service;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.updatedel.common.AjaxResult;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.service.generator.EccKeyGenerator;
import com.ruoyi.updatedel.service.generator.SsclKeyGenerator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * 密钥轮换Service
 * 根据旧版 keymanageServiceImpl.rotateKeyById 适配
 */
@Service
public class KeyRotateService {

    private static final Logger log = LoggerFactory.getLogger(KeyRotateService.class);

    @Autowired
    private KeymanageMapper keymanageMapper;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EccKeyGenerator eccKeyGenerator;

    @Autowired
    private SsclKeyGenerator ssclKeyGenerator;

    /**
     * 根据KeyId轮换密钥
     * 逻辑：查旧数据 -> 版本+1 -> 重新生成密钥 -> 更新数据库 -> 发送上链任务(ROTATE)
     */
    public AjaxResult rotateKeyById(Long keyId) {
        if (keyId == null || keyId <= 0) {
            return AjaxResult.error("keyId 参数非法");
        }

        // 1. 查旧数据
        Keymanage keymanage = keymanageMapper.selectkeymanageByKeyId(keyId);
        if (keymanage == null) {
            log.warn("KeyId {} 不存在，无法轮换", keyId);
            return AjaxResult.error("keyId 不存在");
        }

        // 2. 版本号 +1
        keymanage.setVersion(keymanage.getVersion() != null ? keymanage.getVersion() + 1 : 2);

        // 3. 状态重置
        String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        keymanage.setUpdTime(now);
        keymanage.setStatus(KeyStatus.ACTIVE.getCode());
        keymanage.setChainStatus("0");

        // 4. 重新生成密钥值
        generateKeyLogic(keymanage);

        // 5. 更新数据库
        int rows = keymanageMapper.updatekeymanage(keymanage);

        // 6. 发送上链任务 (ROTATE)
        if (rows > 0) {
            sendChainTask(ChainSyncEvent.TYPE_ROTATE, keymanage);
            log.info("密钥轮换成功: keyId={}, version={}", keyId, keymanage.getVersion());
            return AjaxResult.success("密钥轮换成功");
        }

        return AjaxResult.error("密钥轮换失败，数据库更新行数为0");
    }

    private void sendChainTask(String actionType, Keymanage keymanage) {
        try {
            ChainSyncEvent event = new ChainSyncEvent(actionType, java.util.Collections.singletonList(keymanage));
            kafkaTemplate.send("key_chain_task", JSON.toJSONString(event));
            log.info("已发送上链任务: {} ID={}", actionType, keymanage.getKeyId());
        } catch (Exception e) {
            log.error("发送上链任务异常: actionType={}, keyId={}", actionType, keymanage.getKeyId(), e);
        }
    }

    /**
     * 核心密钥生成逻辑
     */
    private void generateKeyLogic(Keymanage keymanage) {
        if ("对称加密".equals(keymanage.getEncrytType()) && "AES".equals(keymanage.getEncrytName())) {
            try {
                KeyGenerator keyGen = KeyGenerator.getInstance("AES");
                keyGen.init(256);
                SecretKey secretKey = keyGen.generateKey();
                keymanage.setKeyValue(bytesToHex(secretKey.getEncoded()));
            } catch (NoSuchAlgorithmException e) {
                log.error("AES密钥生成失败", e);
            }
        } else if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SM2".equals(keymanage.getEncrytName())) {
            String ua = keymanage.getUa();
            if (ua != null && !ua.isEmpty()) {
                String keyValue = eccKeyGenerator.generate(keymanage.getUserName(), ua);
                keymanage.setKeyValue(keyValue);
            }
        } else if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SSCL".equals(keymanage.getEncrytName())) {
            String ua = keymanage.getUa();
            if (ua != null && !ua.isEmpty()) {
                String keyValue = ssclKeyGenerator.generate(keymanage.getUserName(), ua, keymanage.getKeyDomain());
                keymanage.setKeyValue(keyValue);
            }
        }
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }
}
