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

                // 3. 校验用户存在性
                // 安全边界已上移到 Go 入站层：身份由 Java 业务层经 X-Kms-User 内部头传递，
                // Go 不再信任请求体中的 user，且入站路由不对外暴露。
                // 因此此处不再以「密码为空」作为可信判据（那正是先前的鉴权绕过点）。
                String rawUser = payload.getRawUser();
                GenerateUser user = generateUserService.selectByUserName(rawUser);
                if (user == null) {
                    log.warn("生成消息用户不存在，丢弃: {}", rawUser);
                    continue;
                }
                // 注意：KeyEnrollPayload 里**不再有明文口令字段**。
                // 生产端已停止投递 raw_password（消费端本来就忽略它，而 Kafka 是 PLAINTEXT）。
                // 历史遗留消息里若还带该字段，Jackson 默认忽略未知字段，不会报错。

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
                km.setAutoUpdate(normalizeAutoUpdate(km.getAutoUpdate()));
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

    /**
     * 统一 autoUpdate 字段为 "0"/"1"，与 kms-updatedel 的 LifecycleService 保持一致
     * 避免生成系统存 "true"/"false"、生命周期系统按 "1"/"0" 查询导致自动更新失效
     */
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
}
