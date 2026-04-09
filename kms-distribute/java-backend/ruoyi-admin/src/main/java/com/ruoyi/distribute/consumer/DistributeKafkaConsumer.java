package com.ruoyi.distribute.consumer;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.utils.DateUtils;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.distribute.domain.KeyDistributeRecord;
import com.ruoyi.distribute.domain.Keymanage;
import com.ruoyi.distribute.mapper.KeySnapshotMapper;
import com.ruoyi.distribute.service.IKeyDistributeService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;
import com.ruoyi.system.mapper.SysUserMapper;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * 密钥分发系统 Kafka 消费者
 * 监听生成、更新、回收 topic，自动记录分发信息
 * 分发类型: 1=初始分发(ENROLL_KEY), 2=更新分发(UPDATE_KEY), 3=回收后补发
 */
@Component
public class DistributeKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(DistributeKafkaConsumer.class);
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    @Autowired
    private IKeyDistributeService keyDistributeService;

    @Autowired
    private SysUserMapper sysUserMapper;

    @Autowired
    private KeySnapshotMapper keySnapshotMapper;

    /**
     * 消费生成和生命周期日志，按当前消息协议生成分发记录
     */
    @KafkaListener(
            topics = {
                    "${kms.kafka.generate-topic:key_generate_log}",
                    "${kms.kafka.update-topic:key_update_log}",
                    "${kms.kafka.revoke-topic:key_revoke_log}"
            },
            groupId = "${spring.kafka.consumer.group-id:kms-distribute-consumer-group}",
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
                JSONObject payload = JSON.parseObject(jsonString);
                String actionType = payload.getString("action_type");
                SysUser user = authorize(payload);
                if (user == null) {
                    log.warn("分发消息用户鉴权失败: topic={}, actionType={}, rawUser={}",
                            record.topic(), actionType, payload.getString("raw_user"));
                    continue;
                }

                Keymanage key = resolveKey(record.topic(), payload, user);

                if (key == null) {
                    log.warn("分发消息缺少有效密钥快照: topic={}, actionType={}", record.topic(), actionType);
                    continue;
                }

                String distributeType = resolveDistributeType(record.topic(), actionType);
                if (distributeType == null) {
                    log.debug("忽略非分发类型消息: topic={}, actionType={}", record.topic(), actionType);
                    continue;
                }

                Date now = DateUtils.getNowDate();
                KeyDistributeRecord distributeRecord = new KeyDistributeRecord();
                distributeRecord.setKeyId(key.getKeyId());
                distributeRecord.setUserId(key.getUserId());
                distributeRecord.setUserName(key.getUserName());
                distributeRecord.setKeyName(key.getKeyName());
                distributeRecord.setEncrytType(key.getEncrytType());
                distributeRecord.setEncrytName(key.getEncrytName());
                distributeRecord.setDistributeType(distributeType);
                distributeRecord.setDistributeStatus("2");
                distributeRecord.setDistributeTime(now);
                distributeRecord.setChainHash(key.getChainHash());
                distributeRecord.setBlockHeight(key.getBlockHeight());
                distributeRecord.setCreateTime(now);

                recordsToInsert.add(distributeRecord);
                log.debug("收到分发事件: topic={}, actionType={}, userName={}, keyName={}",
                        record.topic(), actionType, key.getUserName(), key.getKeyName());

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

    private SysUser authorize(JSONObject payload) {
        String rawUser = payload.getString("raw_user");
        String rawPassword = payload.getString("raw_password");
        if (rawUser == null || rawPassword == null) {
            return null;
        }

        SysUser user = sysUserMapper.selectUserByUserName(rawUser);
        if (user == null || user.getPassword() == null) {
            return null;
        }

        return passwordEncoder.matches(rawPassword, user.getPassword()) ? user : null;
    }

    private Keymanage resolveKey(String topic, JSONObject payload, SysUser user) {
        if ("key_generate_log".equals(topic)) {
            JSONObject generatedKeyPayload = payload.getJSONObject("generated_key");
            Keymanage generatedKey = payload.getObject("generated_key", Keymanage.class);
            if (generatedKey == null) {
                return null;
            }
            fillSnapshotFields(generatedKey, generatedKeyPayload);
            if (generatedKey.getUserId() == null) {
                generatedKey.setUserId(user.getUserId());
            }
            if (generatedKey.getUserName() == null || generatedKey.getUserName().trim().isEmpty()) {
                generatedKey.setUserName(user.getUserName());
            }
            return generatedKey;
        }

        JSONObject keyInfo = payload.getJSONObject("key_info");
        if (keyInfo != null) {
            Keymanage snapshot = keyInfo.to(Keymanage.class);
            fillSnapshotFields(snapshot, keyInfo);
            if (snapshot.getKeyId() == null) {
                snapshot.setKeyId(payload.getLong("key_id"));
            }
            return mergeKeySnapshot(snapshot, user);
        }

        Long keyId = payload.getLong("key_id");
        if (keyId == null) {
            return null;
        }
        Keymanage snapshot = new Keymanage();
        snapshot.setKeyId(keyId);
        return mergeKeySnapshot(snapshot, user);
    }

    private Keymanage mergeKeySnapshot(Keymanage snapshot, SysUser user) {
        Keymanage dbSnapshot = snapshot.getKeyId() == null ? null : keySnapshotMapper.selectKeySnapshotById(snapshot.getKeyId());
        Keymanage resolved = dbSnapshot != null ? dbSnapshot : snapshot;

        if (resolved.getKeyId() == null) {
            resolved.setKeyId(snapshot.getKeyId());
        }
        if (resolved.getUserId() == null) {
            resolved.setUserId(user.getUserId());
        }
        if (resolved.getUserName() == null || resolved.getUserName().trim().isEmpty()) {
            resolved.setUserName(user.getUserName());
        }
        if (resolved.getKeyName() == null && snapshot.getKeyName() != null) {
            resolved.setKeyName(snapshot.getKeyName());
        }
        if (resolved.getEncrytType() == null && snapshot.getEncrytType() != null) {
            resolved.setEncrytType(snapshot.getEncrytType());
        }
        if (resolved.getEncrytName() == null && snapshot.getEncrytName() != null) {
            resolved.setEncrytName(snapshot.getEncrytName());
        }
        if (resolved.getChainHash() == null && snapshot.getChainHash() != null) {
            resolved.setChainHash(snapshot.getChainHash());
        }
        if (resolved.getBlockHeight() == null && snapshot.getBlockHeight() != null) {
            resolved.setBlockHeight(snapshot.getBlockHeight());
        }
        return resolved;
    }

    private void fillSnapshotFields(Keymanage snapshot, JSONObject payload) {
        if (snapshot == null || payload == null) {
            return;
        }

        if (snapshot.getKeyId() == null) {
            snapshot.setKeyId(readLong(payload, "key_id", "keyId"));
        }
        if (snapshot.getUserId() == null) {
            snapshot.setUserId(readLong(payload, "user_id", "userId"));
        }
        if (isBlank(snapshot.getUserName())) {
            snapshot.setUserName(readString(payload, "user_name", "userName"));
        }
        if (isBlank(snapshot.getKeyName())) {
            snapshot.setKeyName(readString(payload, "key_name", "keyName"));
        }
        if (isBlank(snapshot.getEncrytType())) {
            snapshot.setEncrytType(readString(payload, "encryt_type", "encrytType"));
        }
        if (isBlank(snapshot.getEncrytName())) {
            snapshot.setEncrytName(readString(payload, "encryt_name", "encrytName"));
        }
        if (isBlank(snapshot.getChainHash())) {
            snapshot.setChainHash(readString(payload, "chain_hash", "chainHash"));
        }
        if (snapshot.getBlockHeight() == null) {
            snapshot.setBlockHeight(readLong(payload, "block_height", "blockHeight"));
        }
    }

    private String readString(JSONObject payload, String primaryKey, String fallbackKey) {
        String value = payload.getString(primaryKey);
        if (isBlank(value)) {
            value = payload.getString(fallbackKey);
        }
        return value;
    }

    private Long readLong(JSONObject payload, String primaryKey, String fallbackKey) {
        Long value = payload.getLong(primaryKey);
        if (value == null) {
            value = payload.getLong(fallbackKey);
        }
        return value;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String resolveDistributeType(String topic, String actionType) {
        if ("ENROLL_KEY".equals(actionType) || "key_generate_log".equals(topic)) {
            return "1";
        }
        if ("UPDATE_KEY".equals(actionType) || "key_update_log".equals(topic)) {
            return "2";
        }
        if ("REVOKE_KEY".equals(actionType) || "key_revoke_log".equals(topic)) {
            return "3";
        }
        return null;
    }
}
