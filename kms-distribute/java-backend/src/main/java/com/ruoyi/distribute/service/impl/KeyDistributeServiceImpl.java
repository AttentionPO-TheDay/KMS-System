package com.ruoyi.distribute.service.impl;

import com.ruoyi.distribute.domain.KeyDistributeRecord;
import com.ruoyi.distribute.mapper.KeyDistributeMapper;
import com.ruoyi.distribute.service.IKeyDistributeService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import java.util.List;

/**
 * 密钥分发记录Service实现
 */
@Service
public class KeyDistributeServiceImpl implements IKeyDistributeService {

    @Autowired
    private KeyDistributeMapper keyDistributeMapper;

    @Override
    public List<KeyDistributeRecord> selectKeyDistributeRecordList(KeyDistributeRecord record) {
        return keyDistributeMapper.selectKeyDistributeRecordList(record);
    }

    @Override
    public KeyDistributeRecord selectKeyDistributeRecordById(Long recordId) {
        return keyDistributeMapper.selectKeyDistributeRecordById(recordId);
    }

    @Override
    public int insertKeyDistributeRecord(KeyDistributeRecord record) {
        return keyDistributeMapper.insertKeyDistributeRecord(record);
    }

    @Override
    public int insertKeyDistributeRecordBatch(List<KeyDistributeRecord> records) {
        return keyDistributeMapper.insertKeyDistributeRecordBatch(records);
    }

    @Override
    public int updateKeyDistributeRecord(KeyDistributeRecord record) {
        return keyDistributeMapper.updateKeyDistributeRecord(record);
    }

    @Override
    public int deleteKeyDistributeRecordById(Long recordId) {
        return keyDistributeMapper.deleteKeyDistributeRecordById(recordId);
    }
}
