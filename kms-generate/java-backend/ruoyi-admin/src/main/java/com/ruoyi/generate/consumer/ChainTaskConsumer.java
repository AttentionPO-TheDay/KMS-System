package com.ruoyi.generate.consumer;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.generate.audit.GenerateAuditService;
import com.ruoyi.generate.domain.ChainSyncEvent;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateChainService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 上链任务消费者
 * 消费 key_chain_task topic，处理 ENROLL 类型上链任务
 */
@Component
public class ChainTaskConsumer {

    private static final Logger log = LoggerFactory.getLogger(ChainTaskConsumer.class);

    @Autowired
    private GenerateChainService generateChainService;

    @Autowired
    private GenerateAuditService auditService;

    /**
     * 消费 key_chain_task 消息
     * 仅处理 ENROLL 类型（生成上链），忽略 ROTATE/REVOKE/FREEZE
     */
    @KafkaListener(
            topics = "${kms.kafka.chain-topic:key_chain_task}",
            groupId = "kms-generate-chain-consumer-group",
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

                // 1. 解析消息
                ChainSyncEvent event = JSON.parseObject(jsonString, ChainSyncEvent.class);
                if (event == null) {
                    continue;
                }

                String actionType = event.getActionType();
                List<Keymanage> keys = event.getKeys();

                if (keys == null || keys.isEmpty()) {
                    continue;
                }

                // 2. 仅处理 ENROLL 类型（生成上链）
                if (!ChainSyncEvent.TYPE_ENROLL.equals(actionType)) {
                    log.debug("忽略非 ENROLL 上链任务: actionType={}", actionType);
                    continue;
                }

                // 3. 处理生成上链
                handleEnroll(keys);

            } catch (Exception e) {
                log.error("上链消息处理异常，Offset: {}", record.offset(), e);
            }
        }
    }

    /**
     * 处理密钥生成上链
     */
    private void handleEnroll(List<Keymanage> keys) {
        for (Keymanage km : keys) {
            try {
                long startTime = System.currentTimeMillis();

                boolean success = generateChainService.processChainSync(km);

                long costTime = System.currentTimeMillis() - startTime;

                // 记录审计日志
                auditService.logChainSync(km.getKeyId(), success, costTime);

                if (success) {
                    log.info("密钥生成上链成功: keyId={}, costTime={}ms", km.getKeyId(), costTime);
                } else {
                    log.error("密钥生成上链失败: keyId={}", km.getKeyId());
                }

            } catch (Exception e) {
                log.error("密钥上链异常: keyId=" + km.getKeyId(), e);
                auditService.logChainSync(km.getKeyId(), false, 0);
            }
        }
    }
}
