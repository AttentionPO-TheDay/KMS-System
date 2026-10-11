package com.ruoyi.updatedel.domain;

import java.util.Date;
import lombok.Data;

/**
 * KMS-019：自动更新（托管轮换）任务的一轮扫描记录。
 *
 * <p>改造前 {@code AutoUpdateTask} 每 60 秒扫一轮候选，成功只记一个内存计数、
 * 失败只有一行 {@code log.warn} —— 「本轮跑了没有 / 成功几条 / 失败几条 /
 * 为什么失败」在任何地方都查不到。本类对应 {@code kms_auto_update_run} 表，
 * 一轮扫描一行。
 *
 * <p>字段口径（与 DDL 注释同一份约定，不许含糊）：
 * <ul>
 *   <li>{@link #candidateCount} —— 本轮**到期**的候选数
 *       （{@code auto_update='1'} 且未回收 且 {@code upd_time<=cutoff}）；</li>
 *   <li>{@link #successCount} / {@link #failCount} —— 逐候选提交轮换的结果，
 *       二者之和等于候选数（每个候选恰好一条 item）；</li>
 *   <li>{@link #skippedCount} —— {@code countAutoUpdateEnabled() - candidateCount}，
 *       即「开着开关、但还没到 interval-minutes 窗口」的密钥数。
 *       <b>它不是错误</b>，也不是"全部密钥里被跳过的部分"，页面文案必须照此解释；</li>
 *   <li>{@link #finishedAt} 为 null 表示这一轮**没有正常跑完**（进程中断/崩溃）——
 *       页面要如实显示"未完成"，不能按 0 成功渲染成一次正常空跑。</li>
 * </ul>
 */
@Data
public class AutoUpdateRun {
    private String runId;
    /** SCHEDULED（定时）/ MANUAL（管理员 run-once 手动补跑）。 */
    private String triggerSource;
    private Date startedAt;
    private Date finishedAt;
    private Integer candidateCount;
    private Integer successCount;
    private Integer failCount;
    private Integer skippedCount;
    private Date createTime;

    /**
     * <b>查询参数，不是表列</b>：非管理员调用时由 Controller 强制填入当前用户，
     * Mapper 用 EXISTS 子查询收敛为「本轮影响过我的密钥」的轮次。
     *
     * <p>⚠️ 不要把它加进 resultMap 或 INSERT 列表 —— 那会得到一个永远为 NULL
     * 的列（与 {@code Keymanage.rotate} 是同一条纪律）。
     */
    private Long userId;
}