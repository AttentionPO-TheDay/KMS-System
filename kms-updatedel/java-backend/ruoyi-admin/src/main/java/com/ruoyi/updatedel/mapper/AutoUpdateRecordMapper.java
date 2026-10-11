package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.AutoUpdateItem;
import com.ruoyi.updatedel.domain.AutoUpdateRun;
import java.util.Date;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * KMS-019：自动更新任务两表（run / item）的 Mapper。
 *
 * <p>两张表**合用一个 Mapper**（而不是各来一套 RuoYi 五件套）：它们是一个聚合
 * —— item 永远属于某个 run，查询也总是成对出现（轮次列表 → 该轮明细）。
 * 拆成两个 Mapper 只会多一份样板，并让"明细要带上轮次上下文"这件事
 * 分散到两个文件里。
 */
@Mapper
public interface AutoUpdateRecordMapper {

    /** 开一轮：只写 run_id / trigger_source / started_at，计数字段先落 0，跑完由 finishRun 回填。 */
    int insertRun(AutoUpdateRun run);

    /**
     * 收一轮：回填结束时间与四个计数。
     *
     * <p>与 {@link #insertRun} 分成两条语句（而不是内存里拼一个完整对象再插入）
     * 是刻意的：进程在扫描中途崩溃时，库里留下的是 finished_at 仍为 NULL 的
     * run 行 —— 页面据此显示"未完成"。若只在最后一次性插入，崩溃会**完全不留痕**，
     * 而"什么都没发生"与"跑了但没跑完"是两种不同的事实。
     */
    int finishRun(@Param("runId") String runId,
                  @Param("finishedAt") Date finishedAt,
                  @Param("candidateCount") int candidateCount,
                  @Param("successCount") int successCount,
                  @Param("failCount") int failCount,
                  @Param("skippedCount") int skippedCount);

    /** 逐候选明细批量插入（调用方按 500 分片，照 KeyOperationRecordService 的做法）。 */
    int insertItems(@Param("items") List<AutoUpdateItem> items);

    /** 轮次列表（倒序）。非管理员时 query.userId 非空 → 收敛为"影响过我密钥的轮次"。 */
    List<AutoUpdateRun> selectRunList(AutoUpdateRun query);

    /** 单轮明细（按 runId 必填；keyId / result / userId 可选筛选），带链上展示字段。 */
    List<AutoUpdateItem> selectItemList(AutoUpdateItem query);

    /**
     * 每把密钥的**最近一条**执行结果（供 keyautoupdate 页「上次执行」列用）。
     *
     * <p>唯一键思路：取每个 key_id 下 item_id 最大的一条。不用"按时间比大小"——
     * updated_at 在批量插入时同秒撞车（同一轮里所有 item 的 updated_at 相同），
     * 比时间会得到不确定的一行；item_id 自增，天然给出确定的"最后一条"。
     */
    List<AutoUpdateItem> selectLatestItemsByKeyIds(@Param("keyIds") List<Long> keyIds,
                                                   @Param("userId") Long userId);
}