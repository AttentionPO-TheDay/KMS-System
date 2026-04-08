package com.ruoyi.keymanage.service;

import java.util.List;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.ruoyi.keymanage.domain.Keymanage;

/**
 * 密钥管理Service接口
 * 
 * @author ruoyi
 * @date 2025-01-14
 */
public interface IKeymanageService
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
     * 获取公共参数
     *
     * @return 公共参数
     */
    public String getComParam(Keymanage keymanage) throws JsonProcessingException;

    /**
     * 新增密钥管理
     * 
     * @param keymanage 密钥管理
     * @return 结果
     */
    public int insertkeymanage(Keymanage keymanage);

    /**
     * 新增密钥管理
     *
     * @param keymanages 密钥管理
     * @return 结果
     */
    public int insertKeymanageBatch(List<Keymanage> keymanages);

    /**
     * 修改密钥管理
     * 
     * @param keymanage 密钥管理
     * @return 结果
     */
    public int updatekeymanage(Keymanage keymanage);

    /**
     * 批量删除密钥管理
     * 
     * @param keyIds 需要删除的密钥管理主键集合
     * @return 结果
     */
    public int deletekeymanageByKeyIds(Long[] keyIds);

    /**
     * 删除密钥管理信息
     * 
     * @param keyId 密钥管理主键
     * @return 结果
     */
    public int deletekeymanageByKeyId(Long keyId);

    public void rotateKeyById(Long keyId);
}
