package com.ruoyi.distribute.mapper;

import com.ruoyi.distribute.domain.KeyDistributeRecord;
import java.util.List;
import org.apache.ibatis.annotations.Param;

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
     * 回填最近一条对应分发类型的链上结果
     */
    int updateLatestChainResultByKeyIdAndType(@Param("keyId") Long keyId,
                                              @Param("distributeType") String distributeType,
                                              @Param("chainHash") String chainHash,
                                              @Param("blockHeight") Long blockHeight,
                                              @Param("remark") String remark);

    /**
     * 删除分发记录
     */
    int deleteKeyDistributeRecordById(Long recordId);
}
