package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.Keymanage;
import java.util.List;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Mapper;

/**
 * 密钥管理Mapper接口
 */
@Mapper
public interface KeymanageMapper {

    /**
     * 查询密钥管理
     *
     * @param keyId 密钥管理主键
     * @return 密钥管理
     */
    Keymanage selectkeymanageByKeyId(Long keyId);

    List<Keymanage> selectMetadataByIds(@Param("keyIds") List<Long> keyIds);

    List<Keymanage> selectRotationCandidates(@Param("userName") String userName,
                                             @Param("keyIds") List<Long> keyIds);

    int archiveRotationBatch(@Param("keyIds") List<Long> keyIds);

    /**
     * 查询密钥管理列表
     *
     * @param keymanage 密钥管理
     * @return 密钥管理集合
     */
    List<Keymanage> selectkeymanageList(Keymanage keymanage);

    /**
     * 新增密钥管理
     *
     * @param keymanage 密钥管理
     * @return 结果
     */
    int insertkeymanage(Keymanage keymanage);

    /**
     * 批量新增密钥管理
     *
     * @param keymanages 密钥管理
     * @return 结果
     */
    int insertKeymanageBatch(List<Keymanage> keymanages);

    /**
     * 修改密钥管理
     *
     * @param keymanage 密钥管理
     * @return 结果
     */
    int updatekeymanage(Keymanage keymanage);

    /**
     * 阶段 4（文档 §5.2）：把密钥的**当前版本**快照归档到版本历史表。
     *
     * <p>调用时机必须是「即将覆盖当前行**之前**」—— 轮换与回收都会改写
     * {@code key_value} / {@code ua} / {@code chain_hash}，不先归档就永久丢失了
     * 旧版本材料，而历史分发记录、会话与链上存证的验证都需要它。
     *
     * <p>实现是 `INSERT ... SELECT`：直接从 keymanage 读当前行写入历史表，
     * 调用方只传 key_id 与归档原因。这样**不存在"Java 侧对象陈旧、
     * 归档了错误快照"的可能** —— 快照内容以数据库当下的行为准，
     * 而不是以调用方内存里的对象为准。
     *
     * <p>幂等：唯一键 (key_id, version)，重复归档同一版本会更新而非报错，
     * 因此整个流程可安全重试。
     *
     * @param keyId  要归档的逻辑密钥 ID
     * @param reason 归档原因：ROTATE（轮换前）/ REVOKE（回收前）
     * @param by     触发来源（MANUAL / AUTO），用于审计
     * @return 归档行数（1 表示成功归档；0 表示该 key_id 不存在）
     */
    int archiveCurrentVersion(@Param("keyId") Long keyId,
                              @Param("reason") String reason,
                              @Param("by") String by);

    /**
     * 查询某逻辑密钥的全部历史版本，按版本号倒序（最新在前）。
     *
     * @param keyId 逻辑密钥 ID
     * @return 历史快照列表；不含当前版本（当前版本仍在 keymanage 表里）
     */
    List<Keymanage> selectVersionHistory(@Param("keyId") Long keyId);

    int updateAutoUpdate(@Param("keyId") Long keyId, @Param("autoUpdate") String autoUpdate);

    int revoke(@Param("keyId") Long keyId, @Param("status") String status);

    List<Keymanage> selectRevokeCandidates(@Param("userName") String userName,
                                           @Param("keyIds") List<Long> keyIds,
                                           @Param("revokedStatus") String revokedStatus);

    int revokeBatch(@Param("userName") String userName,
                    @Param("keyIds") List<Long> keyIds,
                    @Param("status") String status);

    int updateChainStatus(@Param("keyId") Long keyId, @Param("chainStatus") String chainStatus,
                          @Param("chainHash") String chainHash, @Param("blockHeight") Long blockHeight);

    int resetChainState(@Param("keyId") Long keyId, @Param("chainStatus") String chainStatus);

    List<Keymanage> selectAutoUpdateCandidates(@Param("cutoffTime") String cutoffTime);

    int countAutoUpdateEnabled();

    /**
     * KMS-019：把 {@code upd_time} 推进到给定时刻，**不动开关**。
     *
     * <p>用途是自动更新失败后的**退避**：候选 SQL 的条件里含
     * {@code upd_time <= now - interval-minutes}，失败路径原先不推进
     * {@code upd_time}，于是同一条必失败的候选（KYBER/FALCON……）
     * 每 60 秒被重新挑中一次，失败只有一行日志、永不停止。
     * 推进之后，两轮失败之间隔着一个完整的 interval 窗口。
     *
     * <p>为什么不复用 {@link #updateAutoUpdate}：那条 SQL 会同时写
     * {@code auto_update} 列 —— 用一个"改开关"的语句做退避，日后任何一处
     * 传参写错都会**静默把开关改掉**，而页面上的现象是"我没动它它自己关了"。
     *
     * @param keyId   密钥 ID
     * @param updTime 时间串（与 {@code LifecycleService} 的 {@code now()} 同格式，
     *                列本身是 varchar，字符串比较依赖 {@code yyyy-MM-dd HH:mm:ss} 定长排序）
     */
    int touchUpdTime(@Param("keyId") Long keyId, @Param("updTime") String updTime);

    /**
     * KMS-022：批量一致性检查的候选密钥，**keyset 分页**按 key_id 递增读取。
     *
     * <p>只取展示所需的最小列（不含 ua / key_value）：逐钥判定由
     * {@code KeyHealthService.check} 自己回表读全行 —— 这里再读一遍材料，
     * 只是把大字段在内存里多存了一份，而且那一份与判定读到的可能不是同一时刻。
     *
     * <p>用 keyset（{@code key_id > afterKeyId}）而不是 OFFSET：扫描期间密钥
     * 被删除会让 OFFSET 分页**整页跳过**（跳过的那页没人会发现），
     * keyset 只依赖"上一条读到哪"，漏读一行也只影响那一行本身。
     *
     * @param userId     非空 = 只取该用户的密钥（普通用户被强制收敛到此）
     * @param afterKeyId 上一批读到的最大 key_id；首批传 0
     * @param limit      批大小
     */
    List<Keymanage> selectScanTargets(@Param("userId") Long userId,
                                      @Param("afterKeyId") Long afterKeyId,
                                      @Param("limit") int limit);

    /**
     * KMS-022：触顶时统计"还剩多少把没扫"，让 run 行的备注是**一个真实的数**，
     * 而不是一句"可能还有"。
     */
    int countScanTargetsAfter(@Param("userId") Long userId, @Param("afterKeyId") Long afterKeyId);

    /**
     * 删除密钥管理
     *
     * @param keyId 密钥管理主键
     * @return 结果
     */
    int deletekeymanageByKeyId(Long keyId);

    /**
     * 批量删除密钥管理
     *
     * @param keyIds 需要删除的数据主键集合
     * @return 结果
     */
    int deletekeymanageByKeyIds(Long[] keyIds);
}
