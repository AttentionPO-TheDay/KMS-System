package com.ruoyi.updatedel.service;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.updatedel.common.AjaxResult;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Collections;

/**
 * 密钥回收Service
 * 根据旧版 keymanageServiceImpl.deletekeymanageByKeyIds 适配
 */
@Service
public class KeyRevokeService {

    private static final Logger log = LoggerFactory.getLogger(KeyRevokeService.class);

    @Autowired
    private KeymanageMapper keymanageMapper;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    /**
     * 根据KeyId回收密钥
     * 逻辑：先发送上链任务(REVOKE) -> 再更新数据库 status=3 (REVOKED，逻辑删除)
     */
    public AjaxResult revokeKeyById(Long keyId) {
        if (keyId == null || keyId <= 0) {
            return AjaxResult.error("keyId 参数非法");
        }

        // 1. 先发送回收通知 (区块链上记录 REVOKE 事件)
        Keymanage keymanage = new Keymanage();
        keymanage.setKeyId(keyId);
        sendChainTask(ChainSyncEvent.TYPE_REVOKE, keymanage);

        // 2. 更新数据库状态为已回收 (逻辑删除)
        String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        Keymanage updateKey = new Keymanage();
        updateKey.setKeyId(keyId);
        updateKey.setStatus(KeyStatus.REVOKED.getCode());
        updateKey.setUpdTime(now);

        int rows = keymanageMapper.updatekeymanage(updateKey);

        if (rows > 0) {
            log.info("密钥回收成功: keyId={}", keyId);
            return AjaxResult.success("密钥回收成功");
        }

        return AjaxResult.error("密钥回收失败，数据库更新行数为0");
    }

    private void sendChainTask(String actionType, Keymanage keymanage) {
        try {
            ChainSyncEvent event = new ChainSyncEvent(actionType, Collections.singletonList(keymanage));
            kafkaTemplate.send("key_chain_task", JSON.toJSONString(event));
            log.info("已发送上链任务: {} ID={}", actionType, keymanage.getKeyId());
        } catch (Exception e) {
            log.error("发送上链任务异常: actionType={}, keyId={}", actionType, keymanage.getKeyId(), e);
        }
    }
}
