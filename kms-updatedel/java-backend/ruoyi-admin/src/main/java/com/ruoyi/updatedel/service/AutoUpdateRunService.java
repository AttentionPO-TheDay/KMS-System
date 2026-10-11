package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.AutoUpdateItem;
import com.ruoyi.updatedel.domain.AutoUpdateRun;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.AutoUpdateRecordMapper;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * KMS-019：自动更新（托管轮换）任务的执行与查询。
 *
 * <h2>为什么把执行逻辑从这里抽出来</h2>
 * 改造前它是 {@code AutoUpdateTask} 里的一个循环（定时任务私有）。加了
 * {@code POST /lifecycle/auto-update/run-once}（验收与运维补跑都靠它）之后，
 * "跑一轮"就有了两个入口 —— 逻辑再留在任务里，两个入口必然漂移，
 * 而漂移的表现是"手动跑能看到失败原因、等定时跑就看不到"。
 *
 * <h2>为什么这一层<b>不加</b> {@code @Transactional}</h2>
 * 一轮扫描里逐条调用 {@link LifecycleService#rotateKey(Keymanage, String)}
 * （其自身是 REQUIRED 事务）。若在这里再开一个外层事务，内层方法抛异常时
 * Spring 会把**外层事务**标记为 rollback-only —— 即便本类把异常 catch 住
 * 继续跑剩下的候选，最后的提交也会炸成 {@code UnexpectedRollbackException}，
 * 于是"一轮里一条失败"会变成"整轮白跑、run 行永远停在未完成"。
 * 因此这里保持**每条语句各自自动提交**：run 行先落、逐条轮换各自成事务、
 * 明细最后批量写入 —— 中途崩溃时留下的是 finished_at 为 NULL 的 run 行，
 * 那是"跑了但没跑完"的如实记录，而不是静默的全无痕迹。
 */
@Service
public class AutoUpdateRunService {
    private static final Logger log = LoggerFactory.getLogger(AutoUpdateRunService.class);

    /** 失败原因列宽（kms_auto_update_item.reason VARCHAR(500)）。 */
    private static final int REASON_MAX_LENGTH = 500;
    /** 明细批量插入分片大小，与 KeyOperationRecordService 的 500 一致。 */
    private static final int ITEM_CHUNK_SIZE = 500;

    /** 「上次执行」批量查询的 keyId 上限：菜单页一页最多几十行，给足余量即可。 */
    private static final int LATEST_KEYS_MAX = 200;

    public static final String TRIGGER_SCHEDULED = "SCHEDULED";
    public static final String TRIGGER_MANUAL = "MANUAL";
    public static final String RESULT_SUCCESS = "SUCCESS";
    public static final String RESULT_FAILED = "FAILED";

    private final AutoUpdateRecordMapper autoUpdateRecordMapper;
    private final KeymanageMapper keymanageMapper;
    private final LifecycleService lifecycleService;

    public AutoUpdateRunService(AutoUpdateRecordMapper autoUpdateRecordMapper,
                                KeymanageMapper keymanageMapper,
                                LifecycleService lifecycleService) {
        this.autoUpdateRecordMapper = autoUpdateRecordMapper;
        this.keymanageMapper = keymanageMapper;
        this.lifecycleService = lifecycleService;
    }

    /**
     * 跑一轮自动更新：建 run 行 → 逐候选轮换并记 item → 回填计数收尾。
     *
     * @param triggerSource {@link #TRIGGER_SCHEDULED} / {@link #TRIGGER_MANUAL}
     * <p>定时触发与管理员手动触发共享这个单例 service。方法级锁保证同一 JVM
     * 内不会同时读取同一批候选并重复轮换；后续调用会等待前一轮收尾，API
     * 仍返回完整的 run 行，而不是返回一个未执行的假结果。
     *
     * @return 收尾后的 run 行（含四项计数），供 run-once 直接回给调用方
     */
    public synchronized AutoUpdateRun executeOnce(String triggerSource) {
        Date startedAt = new Date();
        AutoUpdateRun run = new AutoUpdateRun();
        run.setRunId(UUID.randomUUID().toString());
        run.setTriggerSource(TRIGGER_MANUAL.equals(triggerSource) ? TRIGGER_MANUAL : TRIGGER_SCHEDULED);
        run.setStartedAt(startedAt);
        autoUpdateRecordMapper.insertRun(run);

        List<Keymanage> candidates = lifecycleService.listAutoUpdateCandidates();
        List<AutoUpdateItem> items = new ArrayList<>(candidates.size());
        int successCount = 0;
        int failCount = 0;
        for (Keymanage candidate : candidates) {
            AutoUpdateItem item = buildItem(run.getRunId(), candidate);
            try {
                Keymanage rotated = lifecycleService.rotateKey(candidate, "AUTO");
                item.setResult(RESULT_SUCCESS);
                // 成功才有"变成几"——轮换后的版本号来自库里的回读结果，
                // 不是内存里 from+1 的推算（推算会把"轮换其实没生效"盖过去）。
                item.setToVersion(rotated.getVersion());
                successCount++;
            } catch (Exception ex) {
                item.setResult(RESULT_FAILED);
                item.setReason(failureReason(ex));
                failCount++;
                // D3 退避：失败也推进 upd_time。不推进的话，候选 SQL
                // （auto_update='1' AND status!='3' AND upd_time<=cutoff）下一轮
                // 仍会命中它 —— KYBER/FALCON 就是"每 60 秒一条 warn、永远成功不了"。
                // 推进后同一条失败变成"每个 interval-minutes 窗口一条失败记录"，
                // 且这次它是**看得见的**（本页的 FAILED 明细 + 原因原文）。
                backoffFailedCandidate(candidate, ex);
            }
            items.add(item);
        }

        // skipped 的口径 = 开着开关还未到期的密钥数（见 AutoUpdateRun 类注释），
        // 出现负数说明两次计数之间密钥被回收/关开关，取 0 而不是把负数写进库里。
        int enabled = keymanageMapper.countAutoUpdateEnabled();
        int skippedCount = Math.max(0, enabled - candidates.size());

        // 轮换已各自提交；明细全部落库后才允许标记完成。写失败直接向上传播，
        // 保留 finished_at=NULL（可能已有部分分片），不能把缺明细的轮次说成完成。
        insertItems(items);
        autoUpdateRecordMapper.finishRun(run.getRunId(), new Date(),
            candidates.size(), successCount, failCount, skippedCount);

        log.info("auto update run finished: runId={}, trigger={}, candidates={}, success={}, fail={}, skipped={}",
            run.getRunId(), run.getTriggerSource(), candidates.size(), successCount, failCount, skippedCount);

        AutoUpdateRun finished = autoUpdateRecordMapper.selectRunList(run).stream().findFirst().orElse(run);
        return finished;
    }

    /** 轮次列表（倒序，分页由 Controller 的 startPage 接管）。 */
    public List<AutoUpdateRun> listRuns(AutoUpdateRun query) {
        return autoUpdateRecordMapper.selectRunList(query);
    }

    /** 单轮明细（带"最近一条 AUTO 流水"的送达/上链展示字段）。 */
    public List<AutoUpdateItem> listItems(AutoUpdateItem query) {
        return autoUpdateRecordMapper.selectItemList(query);
    }

    /**
     * 每把密钥的最近一条执行结果（keyautoupdate 页「上次执行」列）。
     *
     * <p>空列表直接短路：不给 Mapper 一个 `in ()` 的空集合（MySQL 语法错误，
     * 报出来的却是一句与"页面没数据"毫不相干的 SQL 异常）。
     */
    public List<AutoUpdateItem> latestByKeyIds(List<Long> keyIds) {
        return latestByKeyIds(keyIds, null);
    }

    /**
     * 查询最近执行结果；非空 userId 时把查询收敛到该属主。
     * key_id 是可猜的数字，不能把它本身当作授权依据。
     */
    public List<AutoUpdateItem> latestByKeyIds(List<Long> keyIds, Long userId) {
        if (keyIds == null || keyIds.isEmpty()) {
            return Collections.emptyList();
        }
        Set<Long> distinct = new LinkedHashSet<>();
        for (Long keyId : keyIds) {
            if (keyId != null) {
                distinct.add(keyId);
            }
            if (distinct.size() >= LATEST_KEYS_MAX) {
                break;
            }
        }
        if (distinct.isEmpty()) {
            return Collections.emptyList();
        }
        return autoUpdateRecordMapper.selectLatestItemsByKeyIds(new ArrayList<>(distinct), userId);
    }

    private AutoUpdateItem buildItem(String runId, Keymanage candidate) {
        AutoUpdateItem item = new AutoUpdateItem();
        item.setRunId(runId);
        item.setKeyId(candidate.getKeyId());
        // 三个展示字段写入时冗余（照 key_operation_record 的口径）：
        // 列表要按属主收敛、要显示密钥名，回表 join keymanage 既慢，
        // 又会在密钥被改名/删除的瞬间让历史轮次"跟着变"。
        item.setUserId(candidate.getUserId());
        item.setUserName(candidate.getUserName());
        item.setKeyName(candidate.getKeyName());
        item.setEncrytName(candidate.getEncrytName());
        item.setFromVersion(candidate.getVersion());
        item.setUpdatedAt(new Date());
        return item;
    }

    /**
     * 失败原因：异常 message 原文，为空时退到类名（不能把失败记成一行空白 ——
     * 那与"没有原因"看起来一样）。列宽 500，超长截断并显式标注。
     */
    private String failureReason(Exception ex) {
        String message = ex.getMessage();
        if (message == null || message.trim().isEmpty()) {
            message = ex.getClass().getSimpleName();
        }
        return abbreviate(message.trim(), REASON_MAX_LENGTH);
    }

    private String abbreviate(String text, int max) {
        return text.length() <= max ? text : text.substring(0, max - 8) + "...(截断)";
    }

    /**
     * 退避本身**不允许**把整轮带崩：轮换失败已经记进 item 了，退避写不进去
     * 只是"下一轮会被重复挑中"，而抛出去则会让本轮剩下的候选全部不跑。
     */
    private void backoffFailedCandidate(Keymanage candidate, Exception cause) {
        try {
            lifecycleService.backoffAutoUpdateFailure(candidate.getKeyId());
        } catch (Exception backoffEx) {
            log.warn("auto update backoff failed, keyId={}, cause={}", candidate.getKeyId(), cause.toString(), backoffEx);
        }
    }

    private void insertItems(List<AutoUpdateItem> items) {
        for (int i = 0; i < items.size(); i += ITEM_CHUNK_SIZE) {
            List<AutoUpdateItem> chunk = items.subList(i, Math.min(i + ITEM_CHUNK_SIZE, items.size()));
            if (autoUpdateRecordMapper.insertItems(chunk) != chunk.size()) {
                throw new IllegalStateException("自动更新明细未完整落库，runId=" + items.get(0).getRunId());
            }
        }
    }
}