package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.KeyHealthScanItem;
import com.ruoyi.updatedel.domain.KeyHealthScanRun;
import java.util.Date;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * KMS-022：批量一致性检查两表（run / item）的 Mapper。
 *
 * <p>与 KMS-019 的 AutoUpdateRecordMapper 同一条取舍：run 与 item 是一个聚合，
 * 合用一个 Mapper；明细总是"某个 run 的明细"。
 *
 * <p>候选密钥的**分批读取**（keyset 分页）不在这里 —— 它读的是 {@code keymanage}，
 * 归 {@code KeymanageMapper.selectScanTargets}。跨表塞进本 Mapper 会让
 * "谁负责 keymanage"的边界糊掉。
 */
@Mapper
public interface KeyHealthScanMapper {

    /** 开一轮（计数字段先落 0，跑完由 finishRun 回填；中途崩溃留下 finished_at 为 NULL 的行）。 */
    int insertRun(KeyHealthScanRun run);

    /** 收一轮：回填结束时间、四项计数与如实备注。 */
    int finishRun(@Param("runId") String runId,
                  @Param("finishedAt") Date finishedAt,
                  @Param("total") int total,
                  @Param("okCount") int okCount,
                  @Param("warnCount") int warnCount,
                  @Param("errorCount") int errorCount,
                  @Param("note") String note);

    /** 逐钥明细批量插入（调用方按 500 分片）。 */
    int insertItems(@Param("items") List<KeyHealthScanItem> items);

    /**
     * 批次列表（倒序）。
     *
     * <p>非管理员收敛口径（query.userId 非空）：轮次属于自己**或**轮次扫过自己的密钥。
     * 只按前者会漏掉"管理员发起、我的密钥在其中"的批次 —— 那正是普通用户最想看的一类。
     */
    List<KeyHealthScanRun> selectRunList(KeyHealthScanRun query);

    /** 单批明细（runId 必填；verdict / keyId / userId 可选筛选）。 */
    List<KeyHealthScanItem> selectItemList(KeyHealthScanItem query);
}