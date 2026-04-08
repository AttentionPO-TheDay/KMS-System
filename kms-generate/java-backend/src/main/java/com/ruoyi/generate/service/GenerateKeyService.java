package com.ruoyi.generate.service;

import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.Keymanage;
import java.util.List;

/**
 * 生成密钥服务接口
 */
public interface GenerateKeyService {

    /**
     * 查询密钥管理
     * @param keyId 密钥ID
     * @return 密钥管理
     */
    Keymanage selectKeyById(Long keyId);

    /**
     * 查询密钥管理列表
     * @param keymanage 查询条件
     * @return 密钥管理集合
     */
    List<Keymanage> selectKeyList(Keymanage keymanage);

    /**
     * 批量新增密钥
     * @param list 密钥列表
     * @return 插入条数
     */
    int insertKeyBatch(List<Keymanage> list);

    int insertKey(Keymanage keymanage);

    int updateKey(Keymanage keymanage);

    int deleteKey(Long keyId);

    ComParam getComParam(String encrytType, String encrytName);

    /**
     * 更新密钥上链状态
     * @param keyId 密钥ID
     * @param chainStatus 上链状态
     * @param chainHash 区块链交易Hash
     * @param blockHeight 区块高度
     * @return 结果
     */
    int updateChainStatus(Long keyId, String chainStatus, String chainHash, Long blockHeight);
}
