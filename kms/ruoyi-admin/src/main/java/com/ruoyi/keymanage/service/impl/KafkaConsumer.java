package com.ruoyi.keymanage.service.impl;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.common.utils.StringUtils;
import com.ruoyi.keymanage.domain.ChainSyncEvent;
import com.ruoyi.keymanage.domain.KeyPayload;
import com.ruoyi.keymanage.domain.KeyStatus;
import com.ruoyi.keymanage.domain.Keymanage;
import com.ruoyi.keymanage.service.IKeymanageService;
import com.ruoyi.system.domain.SysOperLog;
import com.ruoyi.system.service.ISysOperLogService;
import com.ruoyi.keyuser.domain.KeyUser;
import com.ruoyi.keyuser.service.IKeyUserService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class KafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(KafkaConsumer.class);

    @Autowired
    private IKeyUserService keyUserService;

    @Autowired
    private IKeymanageService keymanageService;

    @Autowired
    private ISysOperLogService operLogService;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    // 缓存1：用户信息缓存
    private final Map<String, KeyUser> userCache = new ConcurrentHashMap<>();

    // 缓存2：已验证通过的明文密码
    private final Map<String, String> verifiedPasswordCache = new ConcurrentHashMap<>();

    @KafkaListener(topics = "go_key_manage_log", groupId = "ruoyi-key-consumer-group")
    public void onMessage(List<ConsumerRecord<String, String>> records) {

        long batchStartTime = System.currentTimeMillis();

        // 这个List只用于收集 ENROLL (新增) 的数据，进行批量入库
        List<Keymanage> validKeysToInsert = new ArrayList<>();

        for (ConsumerRecord<String, String> record : records) {
            String jsonString = record.value();
            if (StringUtils.isEmpty(jsonString)) continue;

            try {
                // 1. 反序列化
                KeyPayload payload = JSON.parseObject(jsonString, KeyPayload.class);
                String username = payload.getRawUser();
                String rawPassword = payload.getRawPassword();
                String actionType = payload.getActionType();

                // 2. 获取用户
                KeyUser user = getUserFromCacheOrDB(username);
                if (user == null) {
                    log.warn("用户不存在: {}", username);
                    continue;
                }

                // 3. 鉴权逻辑
                boolean isAuthPassed = false;
                String cachedPass = verifiedPasswordCache.get(username);
                if (cachedPass != null && cachedPass.equals(rawPassword)) {
                    isAuthPassed = true;
                } else if (SecurityUtils.matchesPassword(rawPassword, user.getPassword())) {
                    isAuthPassed = true;
                    verifiedPasswordCache.put(username, rawPassword);
                }

                if (!isAuthPassed) {
                    log.warn("鉴权失败：密码错误 User: {}", username);
                    continue;
                }

                // 4. 提取数据对象
                Keymanage km = payload.getGeneratedKey();
                if (km == null) continue;

                if (km.getUserName() == null) km.setUserName(username);
                km.setUserId(user.getUserId());

                // =========================================================
                // 【核心分流逻辑】 + 【独立日志记录】
                // =========================================================

                // Case 1: 密钥新增 (ENROLL) - 收集后批量处理
                if ("ENROLL_KEY".equals(actionType)) {
                    km.setVersion(1);
                    km.setStatus(KeyStatus.ACTIVE.getCode());
                    if (km.getAutoUpdate() == null) km.setAutoUpdate("false");
                    validKeysToInsert.add(km);
                }
                // Case 2: 密钥轮换 (UPDATE) - 立即处理并记录日志
                else if ("UPDATE_KEY".equals(actionType)) {
                    if (km.getKeyId() != null && km.getKeyId() > 0) {
                        try {
                            long opStart = System.currentTimeMillis();
                            keymanageService.rotateKeyById(km.getKeyId());
                            long cost = System.currentTimeMillis() - opStart;

                            log.info("密钥轮换成功 ID: {}", km.getKeyId());
                            // ✅ 记录轮换日志 (Type=2 Update)
                            recordSysOperLog("密钥轮换(Kafka)", 2, "KeyID: " + km.getKeyId(), cost);
                        } catch (Exception e) {
                            log.error("轮换失败 ID: " + km.getKeyId(), e);
                        }
                    } else {
                        log.warn("UPDATE_KEY 操作缺少 keyId");
                    }
                }
                // Case 3: 密钥回收 (REVOKE) - 立即处理并记录日志
                else if ("REVOKE_KEY".equals(actionType)) {
                    if (km.getKeyId() != null && km.getKeyId() > 0) {
                        try {
                            long opStart = System.currentTimeMillis();
                            keymanageService.deletekeymanageByKeyId(km.getKeyId());
                            long cost = System.currentTimeMillis() - opStart;

                            log.info("密钥回收成功 ID: {}", km.getKeyId());
                            // ✅ 记录回收日志 (Type=3 Delete)
                            recordSysOperLog("密钥回收(Kafka)", 3, "KeyID: " + km.getKeyId(), cost);
                        } catch (Exception e) {
                            log.error("回收失败 ID: " + km.getKeyId(), e);
                        }
                    } else {
                        log.warn("REVOKE_KEY 操作缺少 keyId");
                    }
                }

            } catch (Exception e) {
                log.error("处理单条消息异常: {}", e.getMessage());
            }
        }

        // 5. 统一处理批量新增 (ENROLL)
        if (!validKeysToInsert.isEmpty()) {
            try {
                // A. 批量入库
                int rows = keymanageService.insertKeymanageBatch(validKeysToInsert);

                long costTime = System.currentTimeMillis() - batchStartTime;
                log.info("批量生成入库 {} 条，耗时 {} ms ", rows, costTime);

                // ✅ 记录批量生成日志 (Type=1 Insert)
                String param = String.format("{\"batchSize\": %d}", rows);
                recordSysOperLog("密钥批量生成(Kafka)", 1, param, costTime);

                // B. 发送上链
                ChainSyncEvent event = new ChainSyncEvent(ChainSyncEvent.TYPE_ENROLL, validKeysToInsert);
                kafkaTemplate.send("key_chain_task", JSON.toJSONString(event));

            } catch (Exception e) {
                log.error("批量入库失败", e);
            }
        }
    }

    /**
     * ✅ 通用日志记录方法
     * @param title 模块标题 (如：密钥轮换)
     * @param businessType 业务类型 (1=新增, 2=修改, 3=删除)
     * @param operParam 请求参数/备注
     * @param costTime 耗时(ms)
     */
    private void recordSysOperLog(String title, int businessType, String operParam, long costTime) {
        try {
            SysOperLog operLog = new SysOperLog();
            operLog.setTitle(title);            // 模块标题
            operLog.setBusinessType(businessType); // 业务类型
            operLog.setOperatorType(0);         // 操作类别 (0=其它, 可以约定为Kafka自动任务)
            operLog.setOperName("System-Kafka");
            operLog.setOperIp("127.0.0.1");
            operLog.setOperLocation("内网自动任务");
            operLog.setMethod("KafkaConsumer.onMessage");
            operLog.setRequestMethod("MQ");     // 请求方式
            operLog.setOperUrl("/kafka/consumer");

            // 参数与结果
            operLog.setOperParam(operParam);
            operLog.setJsonResult("{\"msg\":\"Success\", \"code\":200}");

            operLog.setStatus(0); // 0=正常
            operLog.setErrorMsg(null);
            operLog.setCostTime(costTime);
            operLog.setOperTime(new Date());

            operLogService.insertOperlog(operLog);
        } catch (Exception e) {
            log.error("日志记录失败", e);
        }
    }

    private KeyUser getUserFromCacheOrDB(String username) {
        if (StringUtils.isEmpty(username)) return null;
        if (userCache.containsKey(username)) return userCache.get(username);
        KeyUser query = new KeyUser();
        query.setUserName(username);
        List<KeyUser> users = keyUserService.selectKeyUserList(query);
        if (users != null && !users.isEmpty()) {
            KeyUser user = users.get(0);
            userCache.put(username, user);
            return user;
        }
        return null;
    }
}