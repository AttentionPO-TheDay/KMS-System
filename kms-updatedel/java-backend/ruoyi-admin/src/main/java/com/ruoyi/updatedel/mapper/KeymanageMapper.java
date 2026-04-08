package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.Keymanage;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

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

    int updateAutoUpdate(@Param("keyId") Long keyId, @Param("autoUpdate") String autoUpdate);

    int revoke(@Param("keyId") Long keyId, @Param("status") String status);

    int updateChainStatus(@Param("keyId") Long keyId, @Param("chainStatus") String chainStatus,
                          @Param("chainHash") String chainHash, @Param("blockHeight") Long blockHeight);

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
