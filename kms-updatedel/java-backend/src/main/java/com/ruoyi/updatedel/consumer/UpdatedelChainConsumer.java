package com.ruoyi.updatedel.consumer;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.Keymanage;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 上链任务消费者 (updatedel版本)
 * 消费 key_chain_task topic，处理 ROTATE 和 REVOKE 类型上链任务
 * 与 kms-generate 的 ChainTaskConsumer 并存，分别处理不同类型
 */
@Component
public class UpdatedelChainConsumer {

    private static final Logger log = LoggerFactory.getLogger(UpdatedelChainConsumer.class);

    @KafkaListener(
            topics = "key_chain_task",
            groupId = "kms-updatedel-chain-consumer-group",
            concurrency = "4",
            properties = {
                    "max.poll.records=5",
                    "max.poll.interval.ms=600000"
            }
    )
    public void onMessage(List<ConsumerRecord<String, String>> records) {
        for (ConsumerRecord<String, String> record : records) {
            try {
                String jsonString = record.value();
                if (jsonString == null || jsonString.isEmpty()) {
                    continue;
                }

                ChainSyncEvent event = JSON.parseObject(jsonString, ChainSyncEvent.class);
                if (event == null) {
                    continue;
                }

                String actionType = event.getActionType();
                List<Keymanage> keys = event.getKeys();

                if (keys == null || keys.isEmpty()) {
                    continue;
                }

                if (ChainSyncEvent.TYPE_ROTATE.equals(actionType)) {
                    handleRotate(keys);
                } else if (ChainSyncEvent.TYPE_REVOKE.equals(actionType)) {
                    handleRevoke(keys);
                } else {
                    log.debug("UpdatedelChainConsumer 忽略非 ROTATE/REVOKE 消息: actionType={}", actionType);
                }

            } catch (Exception e) {
                log.error("UpdatedelChainConsumer 上链消息处理异常，Offset: {}", record.offset(), e);
            }
        }
    }

    private void handleRotate(List<Keymanage> keys) {
        for (Keymanage km : keys) {
            try {
                log.info("处理密钥轮换上链: keyId={}, version={}", km.getKeyId(), km.getVersion());
                // TODO: 调用具体的上链服务 processChainSync
                // generateChainService.processChainSync(km);
                log.info("密钥轮换上链处理完成: keyId={}", km.getKeyId());
            } catch (Exception e) {
                log.error("密钥轮换上链异常: keyId={}", km.getKeyId(), e);
            }
        }
    }

    private void handleRevoke(List<Keymanage> keys) {
        for (Keymanage km : keys) {
            try {
                log.info("处理密钥回收上链: keyId={}", km.getKeyId());
                // TODO: 调用具体的上链服务 processChainSync
                // generateChainService.processChainSync(km);
                log.info("密钥回收上链处理完成: keyId={}", km.getKeyId());
            } catch (Exception e) {
                log.error("密钥回收上链异常: keyId={}", km.getKeyId(), e);
            }
        }
    }
}
