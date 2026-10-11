package com.ruoyi.updatedel.domain;

import java.util.Date;
import lombok.Data;

/**
 * KMS-019：自动更新任务里**一个候选密钥**的执行结果。
 *
 * <p>为什么失败原因必须原文落库：改造前的失败只有一行 {@code log.warn}，
 * KYBER/FALCON 这类"服务端根本造不出新版本"的失败与"数据库连接抖动"在界面上
 * 长得一模一样 —— 运维既不知道失败了几条，也不知道为什么。这里把
 * {@code rotateKey} 抛出的异常 message **逐字**记下来。
 *
 * <p>字段来源与口径：
 * <ul>
 *   <li>{@link #userName} / {@link #keyName} / {@link #encrytName} —— 与
 *       {@code key_operation_record} 同样是**写入时冗余**，理由一致：
 *       列表要按属主收敛、要显示密钥名，每次都回表 join {@code keymanage}
 *       既慢又会在密钥被改名的瞬间让历史轮次"跟着变"；</li>
 *   <li>{@link #toVersion} 仅 SUCCESS 有值（轮换后的版本号）；FAILED 时
 *       版本没有变化，为 null —— 不填"预期要变成几"，那是编造；</li>
 *   <li>{@code chainResultStatus} / {@code chainHash} / {@code blockHeight}
 *       （见 {@link #chainResultStatus}）是**读时 join** 的展示字段，
 *       不落库：它们来自 {@code key_operation_record} 里该密钥最近一条
 *       {@code action_source='AUTO'} 的流水，回答"送链/用户接收"这一段的
 *       最终状态。</li>
 * </ul>
 */
@Data
public class AutoUpdateItem {
    private Long itemId;
    private String runId;
    private Long keyId;
    private Long userId;
    private String userName;
    private String keyName;
    private String encrytName;
    /** SUCCESS / FAILED。 */
    private String result;
    /** 失败原因原文（异常 message）；SUCCESS 时为 null。 */
    private String reason;
    private Integer fromVersion;
    private Integer toVersion;
    private Date updatedAt;
    private Date createTime;

    // ------------------------------------------------------------------
    // 展示字段：读时从 key_operation_record join（阶段 1 只读关联，不新增回写耦合）
    // ------------------------------------------------------------------

    /**
     * 该密钥**最近一条** AUTO 操作记录的结果状态
     * （{@code key_operation_record.result_status}：0 处理中 / 1 成功 / 2 失败）。
     *
     * <p>⚠️ 语义边界：它回答的是"这把密钥最近一次自动更新的链上/送达结果"，
     * <b>不保证属于本 run</b> —— {@code key_operation_record} 没有轮次字段
     * （KMS-019 刻意不改它，见计划 §3「阶段 2（可选）」）。页面上写清这一点，
     * 不要让用户读成"本轮的送达状态"。
     */
    private String chainResultStatus;
    private String chainHash;
    private Long blockHeight;

    // ------------------------------------------------------------------
    // 查询参数说明（没有额外字段）
    // ------------------------------------------------------------------
    // 明细列表的筛选**复用上方已有的列**：runId 定位轮次、keyId 定位密钥、
    // result 只看成功/失败；非管理员由 Controller 把 userId 强制填成当前用户。
    // 这与 KeyOperationRecordController:28-30 的收敛写法一致 —— 另开一组
    // "筛选专用字段"会引入"列表按 A 收敛、页面又按 B 过滤"的双口径。
}