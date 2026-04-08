package com.ruoyi.generate.mapper;

import com.ruoyi.generate.domain.Keymanage;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * 密钥管理Mapper接口
 */
@Mapper
public interface KeymanageMapper {

    /**
     * 查询密钥管理
     * @param keyId 密钥ID
     * @return 密钥管理
     */
    Keymanage selectkeymanageByKeyId(Long keyId);

    /**
     * 查询密钥管理列表
     * @param keymanage 查询条件
     * @return 密钥管理集合
     */
    List<Keymanage> selectkeymanageList(Keymanage keymanage);

    /**
     * 新增密钥管理
     * @param keymanage 密钥管理
     * @return 结果
     */
    int insertkeymanage(Keymanage keymanage);

    /**
     * 批量新增密钥管理
     * @param list 密钥管理列表
     * @return 结果
     */
    int insertKeymanageBatch(List<Keymanage> list);

    /**
     * 修改密钥管理
     * @param keymanage 密钥管理
     * @return 结果
     */
    int updatekeymanage(Keymanage keymanage);

    /**
     * 删除密钥管理
     * @param keyId 密钥ID
     * @return 结果
     */
    int deletekeymanageByKeyId(Long keyId);
}
