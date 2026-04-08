package com.ruoyi.generate.service.impl;

import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.mapper.KeymanageMapper;
import com.ruoyi.generate.service.GenerateKeyService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 生成密钥服务实现
 */
@Service
public class GenerateKeyServiceImpl implements GenerateKeyService {

    private static final Logger log = LoggerFactory.getLogger(GenerateKeyServiceImpl.class);

    @Autowired
    private KeymanageMapper keymanageMapper;

    @Override
    public Keymanage selectKeyById(Long keyId) {
        return keymanageMapper.selectkeymanageByKeyId(keyId);
    }

    @Override
    public List<Keymanage> selectKeyList(Keymanage keymanage) {
        return keymanageMapper.selectkeymanageList(keymanage);
    }

    @Override
    public int insertKeyBatch(List<Keymanage> list) {
        if (list == null || list.isEmpty()) {
            return 0;
        }
        int rows = keymanageMapper.insertKeymanageBatch(list);
        log.info("批量插入密钥 {} 条", rows);
        return rows;
    }

    @Override
    public int updateChainStatus(Long keyId, String chainStatus, String chainHash, Long blockHeight) {
        Keymanage updateKey = new Keymanage();
        updateKey.setKeyId(keyId);
        if (chainStatus != null) {
            updateKey.setChainStatus(chainStatus);
        }
        if (chainHash != null) {
            updateKey.setChainHash(chainHash);
        }
        if (blockHeight != null) {
            updateKey.setBlockHeight(blockHeight);
        }
        return keymanageMapper.updatekeymanage(updateKey);
    }
}
