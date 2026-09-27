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
