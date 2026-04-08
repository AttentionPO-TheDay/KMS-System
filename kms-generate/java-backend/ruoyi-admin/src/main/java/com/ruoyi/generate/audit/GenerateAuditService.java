package com.ruoyi.generate.audit;

import com.ruoyi.generate.domain.SysOperLog;
import com.ruoyi.generate.service.ISysOperLogService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Date;

/**
 * 生成审计日志服务
 * 负责记录生成系统相关的操作审计日志
 */
@Service
public class GenerateAuditService {

    private static final Logger log = LoggerFactory.getLogger(GenerateAuditService.class);

    @Autowired
    private ISysOperLogService operLogService;

    /**
     * 审计日志类型
     */
    public static final int TYPE_INSERT = 1;
    public static final int TYPE_UPDATE = 2;
    public static final int TYPE_DELETE = 3;

    /**
     * 记录生成密钥审计日志
     * @param batchSize 批量大小
     * @param costTime 耗时(ms)
     */
    public void logBatchGenerate(int batchSize, long costTime) {
        SysOperLog operLog = new SysOperLog();
        operLog.setTitle("密钥批量生成(Kafka)");
        operLog.setBusinessType(TYPE_INSERT);
        operLog.setOperName("System-Kafka");
        operLog.setOperIp("127.0.0.1");
        operLog.setMethod("GenerateKafkaConsumer.onMessage");
        operLog.setRequestMethod("MQ");
        operLog.setOperUrl("/kafka/consumer/key_generate_log");
        operLog.setOperParam("{\"batchSize\": " + batchSize + "}");
        operLog.setJsonResult("{\"msg\":\"Success\", \"code\":200}");
        operLog.setStatus(0);
        operLog.setCostTime(costTime);
        operLog.setOperTime(new Date());

        saveAuditLog(operLog);
        log.info("审计日志已记录: 密钥批量生成, batchSize={}, costTime={}ms", batchSize, costTime);
    }

    /**
     * 记录上链审计日志
     * @param keyId 密钥ID
     * @param success 是否成功
     * @param costTime 耗时(ms)
     */
    public void logChainSync(Long keyId, boolean success, long costTime) {
        SysOperLog operLog = new SysOperLog();
        operLog.setTitle(success ? "密钥上链成功" : "密钥上链失败");
        operLog.setBusinessType(success ? TYPE_INSERT : TYPE_UPDATE);
        operLog.setOperName("System-ChainConsumer");
        operLog.setOperIp("127.0.0.1");
        operLog.setMethod("GenerateChainConsumer.handleEnroll");
        operLog.setRequestMethod("MQ");
        operLog.setOperUrl("/kafka/consumer/key_chain_task");
        operLog.setOperParam("{\"keyId\": " + keyId + "}");
        operLog.setJsonResult("{\"msg\":\"" + (success ? "Success" : "Failed") + "\", \"code\":" + (success ? 200 : 500) + "}");
        operLog.setStatus(success ? 0 : 1);
        operLog.setErrorMsg(success ? null : "上链失败");
        operLog.setCostTime(costTime);
        operLog.setOperTime(new Date());

        saveAuditLog(operLog);
        log.info("审计日志已记录: 密钥上链, keyId={}, success={}, costTime={}ms", keyId, success, costTime);
    }

    /**
     * 记录消费消息审计日志
     * @param topic Topic名称
     * @param partition 分区
     * @param offset 偏移量
     * @param actionType 动作类型
     * @param success 是否成功
     */
    public void logConsumeMessage(String topic, int partition, long offset, String actionType, boolean success) {
        SysOperLog operLog = new SysOperLog();
        operLog.setTitle("Kafka消息消费");
        operLog.setBusinessType(TYPE_INSERT);
        operLog.setOperName("System-Kafka");
        operLog.setOperIp("127.0.0.1");
        operLog.setMethod("GenerateKafkaConsumer.onMessage");
        operLog.setRequestMethod("MQ");
        operLog.setOperUrl("/kafka/consumer/" + topic);
        operLog.setOperParam("{\"topic\":\"" + topic + "\", \"partition\":" + partition + ", \"offset\":" + offset + ", \"actionType\":\"" + actionType + "\"}");
        operLog.setJsonResult("{\"msg\":\"" + (success ? "Consumed" : "Failed") + "\", \"code\":" + (success ? 200 : 500) + "}");
        operLog.setStatus(success ? 0 : 1);
        operLog.setCostTime(0L);
        operLog.setOperTime(new Date());

        saveAuditLog(operLog);
    }

    /**
     * 保存审计日志到数据库
     */
    private void saveAuditLog(SysOperLog operLog) {
        try {
            operLogService.insertOperlog(operLog);
        } catch (Exception e) {
            log.error("审计日志保存失败: title={}, businessType={}, operName={}, status={}, costTime={}",
                    operLog.getTitle(),
                    operLog.getBusinessType(),
                    operLog.getOperName(),
                    operLog.getStatus(),
                    operLog.getCostTime(),
                    e);
        }
    }
}