package com.ruoyi.updatedel.task;

import com.ruoyi.updatedel.domain.AutoUpdateRun;
import com.ruoyi.updatedel.service.AutoUpdateRunService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 自动更新（托管轮换）的定时触发。
 *
 * <p>KMS-019 之后本类**只负责触发**：一轮扫描的建 run 行、逐候选写
 * 成功/失败明细、失败退避、收尾计数全部在 {@link AutoUpdateRunService} 里，
 * 与 {@code POST /lifecycle/auto-update/run-once}（管理员手动补跑）共用同一段代码。
 *
 * <p>改造前这里是 15 行循环：成功只计数、失败只有一行 {@code log.warn}，
 * 失败候选不推进 {@code upd_time} → 每 60 秒重试一次、永远成功不了，
 * 而"跑了没有/失败几条/为什么"任何地方都查不到。
 *
 * <p>本轮执行本身不许把调度器带崩：{@code @Scheduled} 的任务抛异常会被
 * Spring 记 error 日志后**继续**按 fixedDelay 调度，但一轮里的异常若逃逸到
 * 这里，run 行会停在"未完成"。service 内部已对可预期的失败逐条兜住，
 * 这里再兜一层只为止损 —— 失败时如实留一条 error 日志。
 */
@Component
public class AutoUpdateTask {
    private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(AutoUpdateTask.class);

    private final AutoUpdateRunService autoUpdateRunService;

    public AutoUpdateTask(AutoUpdateRunService autoUpdateRunService) {
        this.autoUpdateRunService = autoUpdateRunService;
    }

    @Scheduled(fixedDelayString = "${kms.lifecycle.auto-update.scan-delay-ms:60000}")
    public void executeAutoUpdate() {
        try {
            AutoUpdateRun run = autoUpdateRunService.executeOnce(AutoUpdateRunService.TRIGGER_SCHEDULED);
            // 每轮一行：成功数不单独刷屏，失败明细在任务记录页可查（runId 可定位）。
            log.info("auto update executed: runId={}, candidates={}, success={}, fail={}",
                run.getRunId(), run.getCandidateCount(), run.getSuccessCount(), run.getFailCount());
        } catch (Exception ex) {
            log.error("auto update run failed unexpectedly", ex);
        }
    }
}