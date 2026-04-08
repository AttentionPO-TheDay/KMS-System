package com.ruoyi.generate.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Date;

/**
 * 生成审计日志服务
 * 负责记录生成系统相关的操作审计日志
 */
@Service
public class GenerateAuditService {

    private static final Logger log = LoggerFactory.getLogger(GenerateAuditService.class);

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
        GenerateAuditLog auditLog = new GenerateAuditLog();
        auditLog.setTitle("密钥批量生成(Kafka)");
        auditLog.setBusinessType(TYPE_INSERT);
        auditLog.setOperName("System-Kafka");
        auditLog.setOperIp("127.0.0.1");
        auditLog.setMethod("GenerateKafkaConsumer.onMessage");
        auditLog.setRequestMethod("MQ");
        auditLog.setOperUrl("/kafka/consumer/key_generate_log");
        auditLog.setOperParam("{\"batchSize\": " + batchSize + "}");
        auditLog.setJsonResult("{\"msg\":\"Success\", \"code\":200}");
        auditLog.setStatus(0);
        auditLog.setCostTime(costTime);
        auditLog.setOperTime(new Date());

        saveAuditLog(auditLog);
        log.info("审计日志已记录: 密钥批量生成, batchSize={}, costTime={}ms", batchSize, costTime);
    }

    /**
     * 记录上链审计日志
     * @param keyId 密钥ID
     * @param success 是否成功
     * @param costTime 耗时(ms)
     */
    public void logChainSync(Long keyId, boolean success, long costTime) {
        GenerateAuditLog auditLog = new GenerateAuditLog();
        auditLog.setTitle(success ? "密钥上链成功" : "密钥上链失败");
        auditLog.setBusinessType(success ? TYPE_INSERT : TYPE_UPDATE);
        auditLog.setOperName("System-ChainConsumer");
        auditLog.setOperIp("127.0.0.1");
        auditLog.setMethod("GenerateChainConsumer.handleEnroll");
        auditLog.setRequestMethod("MQ");
        auditLog.setOperUrl("/kafka/consumer/key_chain_task");
        auditLog.setOperParam("{\"keyId\": " + keyId + "}");
        auditLog.setJsonResult("{\"msg\":\"" + (success ? "Success" : "Failed") + "\", \"code\":" + (success ? 200 : 500) + "}");
        auditLog.setStatus(success ? 0 : 1);
        auditLog.setErrorMsg(success ? null : "上链失败");
        auditLog.setCostTime(costTime);
        auditLog.setOperTime(new Date());

        saveAuditLog(auditLog);
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
        GenerateAuditLog auditLog = new GenerateAuditLog();
        auditLog.setTitle("Kafka消息消费");
        auditLog.setBusinessType(TYPE_INSERT);
        auditLog.setOperName("System-Kafka");
        auditLog.setOperIp("127.0.0.1");
        auditLog.setMethod("GenerateKafkaConsumer.onMessage");
        auditLog.setRequestMethod("MQ");
        auditLog.setOperUrl("/kafka/consumer/" + topic);
        auditLog.setOperParam("{\"topic\":\"" + topic + "\", \"partition\":" + partition + ", \"offset\":" + offset + ", \"actionType\":\"" + actionType + "\"}");
        auditLog.setJsonResult("{\"msg\":\"" + (success ? "Consumed" : "Failed") + "\", \"code\":" + (success ? 200 : 500) + "}");
        auditLog.setStatus(success ? 0 : 1);
        auditLog.setCostTime(0);
        auditLog.setOperTime(new Date());

        saveAuditLog(auditLog);
    }

    /**
     * 保存审计日志（这里简化处理，实际应存入数据库或日志系统）
     */
    private void saveAuditLog(GenerateAuditLog auditLog) {
        // 实际实现中可以存入数据库、ElasticSearch或文件
        // 这里仅记录到日志
        log.debug("AuditLog: title={}, businessType={}, operName={}, status={}, costTime={}",
                auditLog.getTitle(),
                auditLog.getBusinessType(),
                auditLog.getOperName(),
                auditLog.getStatus(),
                auditLog.getCostTime());
    }

    /**
     * 审计日志对象
     */
    public static class GenerateAuditLog {
        private String title;
        private int businessType;
        private String operName;
        private String operIp;
        private String method;
        private String requestMethod;
        private String operUrl;
        private String operParam;
        private String jsonResult;
        private int status;
        private String errorMsg;
        private long costTime;
        private Date operTime;

        // Getters and Setters
        public String getTitle() { return title; }
        public void setTitle(String title) { this.title = title; }

        public int getBusinessType() { return businessType; }
        public void setBusinessType(int businessType) { this.businessType = businessType; }

        public String getOperName() { return operName; }
        public void setOperName(String operName) { this.operName = operName; }

        public String getOperIp() { return operIp; }
        public void setOperIp(String operIp) { this.operIp = operIp; }

        public String getMethod() { return method; }
        public void setMethod(String method) { this.method = method; }

        public String getRequestMethod() { return requestMethod; }
        public void setRequestMethod(String requestMethod) { this.requestMethod = requestMethod; }

        public String getOperUrl() { return operUrl; }
        public void setOperUrl(String operUrl) { this.operUrl = operUrl; }

        public String getOperParam() { return operParam; }
        public void setOperParam(String operParam) { this.operParam = operParam; }

        public String getJsonResult() { return jsonResult; }
        public void setJsonResult(String jsonResult) { this.jsonResult = jsonResult; }

        public int getStatus() { return status; }
        public void setStatus(int status) { this.status = status; }

        public String getErrorMsg() { return errorMsg; }
        public void setErrorMsg(String errorMsg) { this.errorMsg = errorMsg; }

        public long getCostTime() { return costTime; }
        public void setCostTime(long costTime) { this.costTime = costTime; }

        public Date getOperTime() { return operTime; }
        public void setOperTime(Date operTime) { this.operTime = operTime; }
    }
}
