package com.ruoyi.generate.consumer;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.generate.audit.GenerateAuditService;
import com.ruoyi.generate.domain.ChainSyncEvent;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.KeyPayload;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateChainService;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 生成系统 Kafka 消费者
 * 消费 key_generate_log topic，仅处理 ENROLL_KEY 类型消息
 */
@Component
public class GenerateKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(GenerateKafkaConsumer.class);

    @Autowired
    private GenerateKeyService generateKeyService;

    @Autowired
    private GenerateChainService generateChainService;

    @Autowired
    private GenerateAuditService auditService;

    @Autowired
    private GenerateUserService generateUserService;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Value("${kms.kafka.chain-topic:key_chain_task}")
    private String chainTopic;

    /**
     * 消费 key_generate_log 消息
     * 仅处理 ENROLL_KEY 类型的消息，忽略 UPDATE/REVOKE
     */
    @KafkaListener(
            topics = "${kms.kafka.generate-topic:key_generate_log}",
            groupId = "${spring.kafka.consumer.group-id:kms-generate-consumer-group}",
            properties = {
                    "max.poll.records=500",
                    "max.poll.interval.ms=600000"
            }
    )
    public void onMessage(List<ConsumerRecord<String, String>> records) {
        long batchStartTime = System.currentTimeMillis();

        // 仅收集 ENROLL (新增) 的数据进行批量入库
        List<Keymanage> validKeysToInsert = new ArrayList<>();

        for (ConsumerRecord<String, String> record : records) {
            String jsonString = record.value();
            if (jsonString == null || jsonString.isEmpty()) {
                continue;
            }

            try {
                // 1. 反序列化消息
                KeyPayload payload = JSON.parseObject(jsonString, KeyPayload.class);
                String actionType = payload.getActionType();

                // 2. 仅处理 ENROLL_KEY 类型
                if (!"ENROLL_KEY".equals(actionType)) {
                    log.debug("忽略非 ENROLL_KEY 消息: actionType={}", actionType);
                    continue;
                }

                // 3. 终校验用户身份，避免任何人直接向 Kafka 注入生成消息
                String rawUser = payload.getRawUser();
                String rawPassword = payload.getRawPassword();
                GenerateUser user = generateUserService.selectByUserName(rawUser);
                if (user == null) {
                    log.warn("生成消息用户不存在: {}", rawUser);
                    continue;
                }
                if (!generateUserService.matchesPassword(rawPassword, user.getPassword())) {
                    log.warn("生成消息用户鉴权失败: {}", rawUser);
                    continue;
                }

                // 4. 提取密钥数据
                Keymanage km = payload.getGeneratedKey();
                if (km == null) {
                    log.warn("ENROLL_KEY 消息缺少 generatedKey");
                    continue;
                }

                km.setUserId(user.getUserId());
                if (km.getUserName() == null || km.getUserName().trim().isEmpty()) {
                    km.setUserName(user.getUserName());
                }

                // 5. 设置默认状态
                km.setVersion(1);
                km.setStatus("0"); // ACTIVE
                if (km.getAutoUpdate() == null) {
                    km.setAutoUpdate("false");
                }
                km.setChainStatus("0"); // 待上链

                validKeysToInsert.add(km);
                log.debug("收到 ENROLL_KEY 消息: userName={}, encrytName={}",
                        km.getUserName(), km.getEncrytName());

            } catch (Exception e) {
                log.error("处理单条消息异常: {}", e.getMessage(), e);
            }
        }

        // 5. 统一处理批量新增 (ENROLL)
        if (!validKeysToInsert.isEmpty()) {
            try {
                // A. 批量入库
                long insertStart = System.currentTimeMillis();
                int rows = generateKeyService.insertKeyBatch(validKeysToInsert);
                long insertCost = System.currentTimeMillis() - insertStart;

                log.info("批量生成入库 {} 条，耗时 {} ms", rows, insertCost);

                // B. 记录审计日志
                auditService.logBatchGenerate(rows, insertCost);

                // C. 发送上链任务
                ChainSyncEvent event = new ChainSyncEvent(ChainSyncEvent.TYPE_ENROLL, validKeysToInsert);
                kafkaTemplate.send(chainTopic, JSON.toJSONString(event));
                log.info("已发送上链任务到 {}，类型=ENROLL，数量={}", chainTopic, rows);

            } catch (Exception e) {
                log.error("批量入库失败", e);
            }
        }

        long totalCost = System.currentTimeMillis() - batchStartTime;
        log.debug("本次消费处理完成，耗时 {} ms，有效消息 {} 条",
                totalCost, validKeysToInsert.size());
    }
}
