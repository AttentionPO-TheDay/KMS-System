package com.ruoyi.updatedel.domain;

import java.util.ArrayList;
import java.util.List;

/**
 * 密钥健康检查结果（阶段 7，文档 §8.1 一致性检查 + §8.2 异常检测）。
 *
 * <p>两件事合并成一个结果对象，因为它们**共用同一份数据**（密钥本体 +
 * 操作轨迹 + 版本历史），分成两次查询只是把同样的表扫两遍。
 *
 * <p>设计要点：**不给"总分"**。一个 0-100 的健康分看起来直观，但会掩盖
 * 具体问题——"87 分"无法告诉运维该做什么。这里返回的是
 * {@link #findings} 列表，每条都带可执行的说明；是否有问题看
 * {@link #status}，怎么修看 findings。
 */
public class KeyHealthResult {

    /** 总体结论，取值见下方常量。 */
    public static final String OK = "OK";
    public static final String SUSPICIOUS = "SUSPICIOUS";
    public static final String REVOKED = "REVOKED";

    /** 被检查的密钥 ID。 */
    private Long keyId;
    private String keyName;
    private Integer version;
    private String status;

    /** OK / SUSPICIOUS / REVOKED（文档 §8.2 的状态机 NORMAL → SUSPICIOUS → REVOKED）。 */
    private String health = OK;

    /** 命中的规则列表。空列表表示全部检查通过。 */
    private List<Finding> findings = new ArrayList<>();

    /** 供前端展示的原始观测值，便于人工核对（不参与判定）。 */
    private List<String> observations = new ArrayList<>();

    /**
     * 一条检查结果。
     *
     * @param rule     规则标识，稳定不变，便于前端做映射与统计
     * @param severity INFO / WARN / ERROR
     * @param message  人话说明：**哪里不对、为什么算不对**
     * @param advice   可执行建议。没有建议的告警等于把问题丢回给用户
     */
    public static class Finding {
        private String rule;
        private String severity;
        private String message;
        private String advice;

        public Finding(String rule, String severity, String message, String advice) {
            this.rule = rule;
            this.severity = severity;
            this.message = message;
            this.advice = advice;
        }

        public String getRule() { return rule; }
        public String getSeverity() { return severity; }
        public String getMessage() { return message; }
        public String getAdvice() { return advice; }
    }

    /** 记一条 INFO 级观测（不改变健康结论）。 */
    public void observe(String text) {
        observations.add(text);
    }

    /** 记一条 WARN：把结论拉到 SUSPICIOUS（除非已经是 REVOKED）。 */
    public void warn(String rule, String message, String advice) {
        findings.add(new Finding(rule, "WARN", message, advice));
        if (!REVOKED.equals(health)) {
            health = SUSPICIOUS;
        }
    }

    /** 记一条 ERROR：结论直接置为 REVOKED（不可继续使用）。 */
    public void error(String rule, String message, String advice) {
        findings.add(new Finding(rule, "ERROR", message, advice));
        health = REVOKED;
    }

    public Long getKeyId() { return keyId; }
    public void setKeyId(Long keyId) { this.keyId = keyId; }
    public String getKeyName() { return keyName; }
    public void setKeyName(String keyName) { this.keyName = keyName; }
    public Integer getVersion() { return version; }
    public void setVersion(Integer version) { this.version = version; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getHealth() { return health; }
    public void setHealth(String health) { this.health = health; }
    public List<Finding> getFindings() { return findings; }
    public void setFindings(List<Finding> findings) { this.findings = findings; }
    public List<String> getObservations() { return observations; }
    public void setObservations(List<String> observations) { this.observations = observations; }
}
