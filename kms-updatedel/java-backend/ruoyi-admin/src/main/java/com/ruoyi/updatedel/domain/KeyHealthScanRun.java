package com.ruoyi.updatedel.domain;

import java.util.Date;
import lombok.Data;

/**
 * KMS-022：批量一致性检查的一轮扫描（用户密钥侧）。
 *
 * <p>单钥检查（阶段 7，{@code GET /lifecycle/keymanage/health/{keyId}}）只回答
 * "这一把怎么样"；本类对应 {@code key_health_scan_run} 表，回答"这一批扫了哪些、
 * 结论各是什么"，让结果**可回看、可对比** —— 现算的结果不留痕，两次扫描之间
 * 密钥被修好或改坏就无从对照。
 *
 * <p>扫描是**只读**操作：它不改任何密钥状态，处置仍走各密钥自己的更新/回收接口。
 * 因此这里的计数不是"处置进度"，页面文案必须照此解释。
 *
 * <p>{@link #note} 是如实口：单次扫描有条数上限（默认 2000，可配置），
 * 触顶时这里写清"剩余多少把未扫描"，而不是让页面的"total"冒充全量。
 */
@Data
public class KeyHealthScanRun {
    private String runId;
    /** 非空 = 本次只扫该用户的密钥；空 = 全量（仅管理员可用）。 */
    private Long userId;
    /** ALL / OWNER。 */
    private String scope;
    private Date startedAt;
    private Date finishedAt;
    private Integer total;
    private Integer okCount;
    private Integer warnCount;
    private Integer errorCount;
    /** 如实备注：触顶未扫完、或扫描期间密钥被删除等；无异常时为 null。 */
    private String note;
    private Date createTime;
}