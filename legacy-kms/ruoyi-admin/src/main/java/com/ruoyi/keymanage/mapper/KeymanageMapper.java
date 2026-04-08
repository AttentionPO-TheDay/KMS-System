package com.ruoyi.keymanage.mapper;

import java.util.List;
import com.ruoyi.keymanage.domain.Keymanage;
import org.apache.ibatis.annotations.Mapper;

/**
 * 密钥管理Mapper接口
 * 
 * @author ruoyi
 * @date 2025-01-14
 */
@Mapper
public interface KeymanageMapper
{
    /**
     * 查询密钥管理
     * 
     * @param keyId 密钥管理主键
     * @return 密钥管理
     */
    public Keymanage selectkeymanageByKeyId(Long keyId);

    /**
     * 查询密钥管理列表
     * 
     * @param keymanage 密钥管理
     * @return 密钥管理集合
     */
    public List<Keymanage> selectkeymanageList(Keymanage keymanage);

    /**
     * 新增密钥管理
     * 
     * @param keymanage 密钥管理
     * @return 结果
     */
    public int insertkeymanage(Keymanage keymanage);

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
    public int updatekeymanage(Keymanage keymanage);

    /**
     * 删除密钥管理
     * 
     * @param keyId 密钥管理主键
     * @return 结果
     */
    public int deletekeymanageByKeyId(Long keyId);

    /**
     * 批量删除密钥管理
     * 
     * @param keyIds 需要删除的数据主键集合
     * @return 结果
     */
    public int deletekeymanageByKeyIds(Long[] keyIds);
}
