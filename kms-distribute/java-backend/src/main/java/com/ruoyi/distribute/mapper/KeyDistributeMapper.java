package com.ruoyi.distribute.mapper;

import com.ruoyi.distribute.domain.KeyDistributeRecord;
import java.util.List;

/**
 * 密钥分发记录Mapper接口
 */
public interface KeyDistributeMapper {

    /**
     * 查询分发记录列表
     */
    List<KeyDistributeRecord> selectKeyDistributeRecordList(KeyDistributeRecord record);

    /**
     * 查询分发记录byID
     */
    KeyDistributeRecord selectKeyDistributeRecordById(Long recordId);

    /**
     * 新增分发记录
     */
    int insertKeyDistributeRecord(KeyDistributeRecord record);

    /**
     * 批量新增分发记录
     */
    int insertKeyDistributeRecordBatch(List<KeyDistributeRecord> records);

    /**
     * 更新分发记录
     */
    int updateKeyDistributeRecord(KeyDistributeRecord record);

    /**
     * 删除分发记录
     */
    int deleteKeyDistributeRecordById(Long recordId);
}
