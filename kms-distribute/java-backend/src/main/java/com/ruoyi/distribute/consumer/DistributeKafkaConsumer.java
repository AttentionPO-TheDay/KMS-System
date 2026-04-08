package com.ruoyi.distribute.consumer;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.distribute.domain.KeyDistributeRecord;
import com.ruoyi.distribute.service.IKeyDistributeService;
import com.ruoyi.generate.domain.KeyPayload;
import com.ruoyi.generate.domain.Keymanage;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * 密钥分发系统 Kafka 消费者
 * 监听 key_generate_log topic，自动记录分发信息
 * 分发类型: 1=初始分发(ENROLL_KEY), 2=更新分发(UPDATE_KEY), 3=回收后补发
 */
@Component
public class DistributeKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(DistributeKafkaConsumer.class);

    @Autowired
    private IKeyDistributeService keyDistributeService;

    /**
     * 消费密钥生成日志，监听 ENROLL_KEY 和 UPDATE_KEY 事件
     */
    @KafkaListener(
            topics = "key_generate_log",
            groupId = "kms-distribute-consumer-group",
            properties = {
                    "max.poll.records=500",
                    "max.poll.interval.ms=600000"
            }
    )
    public void onMessage(List<ConsumerRecord<String, String>> records) {
        long batchStartTime = System.currentTimeMillis();
        List<KeyDistributeRecord> recordsToInsert = new ArrayList<>();

        for (ConsumerRecord<String, String> record : records) {
            String jsonString = record.value();
            if (jsonString == null || jsonString.isEmpty()) {
                continue;
            }

            try {
                KeyPayload payload = JSON.parseObject(jsonString, KeyPayload.class);
                String actionType = payload.getActionType();
                Keymanage key = payload.getGeneratedKey();

                if (key == null) {
                    continue;
                }

                String distributeType;
                switch (actionType) {
                    case "ENROLL_KEY":
                        distributeType = "1"; // 初始分发
                        break;
                    case "UPDATE_KEY":
                        distributeType = "2"; // 更新分发
                        break;
                    case "REVOKE_KEY":
                        distributeType = "3"; // 回收后补发
                        break;
                    default:
                        log.debug("忽略非分发类型消息: actionType={}", actionType);
                        continue;
                }

                KeyDistributeRecord distributeRecord = new KeyDistributeRecord();
                distributeRecord.setKeyId(key.getKeyId());
                distributeRecord.setUserId(key.getUserId());
                distributeRecord.setUserName(key.getUserName());
                distributeRecord.setKeyName(key.getKeyName());
                distributeRecord.setEncrytType(key.getEncrytType());
                distributeRecord.setEncrytName(key.getEncrytName());
                distributeRecord.setDistributeType(distributeType);
                distributeRecord.setDistributeStatus("2"); // 默认成功
                distributeRecord.setDistributeTime(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date()));
                distributeRecord.setChainHash(key.getChainHash());
                distributeRecord.setBlockHeight(key.getBlockHeight());
                distributeRecord.setCreTime(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date()));

                recordsToInsert.add(distributeRecord);
                log.debug("收到分发事件: actionType={}, userName={}, keyName={}",
                        actionType, key.getUserName(), key.getKeyName());

            } catch (Exception e) {
                log.error("处理单条消息异常: {}", e.getMessage(), e);
            }
        }

        // 批量插入分发记录
        if (!recordsToInsert.isEmpty()) {
            try {
                long insertStart = System.currentTimeMillis();
                int rows = keyDistributeService.insertKeyDistributeRecordBatch(recordsToInsert);
                long insertCost = System.currentTimeMillis() - insertStart;

                log.info("批量插入分发记录 {} 条，耗时 {} ms", rows, insertCost);
            } catch (Exception e) {
                log.error("批量插入分发记录失败", e);
            }
        }

        long totalCost = System.currentTimeMillis() - batchStartTime;
        log.debug("本次消费处理完成，耗时 {} ms，有效消息 {} 条",
                totalCost, recordsToInsert.size());
    }
}
