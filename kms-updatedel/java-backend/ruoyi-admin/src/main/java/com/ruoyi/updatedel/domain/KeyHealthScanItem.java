package com.ruoyi.updatedel.domain;

import java.util.Date;
import lombok.Data;

/**
 * KMS-022：批量一致性检查里**一把密钥**的判定结果。
 *
 * <h2>verdict 的口径（与 KeyHealthResult 的关系，必须写清楚）</h2>
 * 判定**只看 findings 的严重级**，不看 {@code health} 字段：
 * <ul>
 *   <li>任一 finding 为 ERROR → {@code ERROR}；</li>
 *   <li>否则任一 finding 为 WARN → {@code WARN}；</li>
 *   <li>没有任何 finding → {@code OK}。</li>
 * </ul>
 * 为什么不直接用 {@code health}：{@code KeyHealthResult.REVOKED} 同时被两种情形
 * 置位 —— "材料缺失（真异常）"与"密钥已回收（正常终态，checkRevoked 直接置
 * REVOKED 但不产生任何 finding）"。若把 REVOKED 一律算作异常，每次扫描都会把
 * 全部已回收密钥报成 ERROR，异常数被噪声淹没；若一律不算，材料缺失的密钥会被
 * 藏起来。按 findings 分级则两种情形各归各位：材料缺失有 ERROR finding（进
 * error 桶），已回收无 finding（进 ok 桶，{@link #summary} 里如实写明"已回收"）。
 *
 * @see com.ruoyi.updatedel.service.KeyHealthService
 */
@Data
public class KeyHealthScanItem {
    private Long itemId;
    private String runId;
    private Long keyId;
    private Long userId;
    private String userName;
    private String keyName;
    private String encrytName;
    private Integer keyVersion;
    /** OK / WARN / ERROR（口径见类注释）。 */
    private String verdict;
    /** 命中的规则名（逗号连接）；OK 为 null —— 不编造"未命中任何规则"以外的内容。 */
    private String rule;
    /** 规则说明的连接文本；无 finding 时是如实的一句话（含"已回收"这类终态说明）。 */
    private String summary;
    private Date createTime;
}