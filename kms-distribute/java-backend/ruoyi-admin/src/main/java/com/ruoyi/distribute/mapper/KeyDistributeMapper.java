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
     * 为最近一条待绑定 keyId 的生成分发记录补绑 keyId 并回填链上结果
     */
    int bindLatestPendingGenerateRecord(@Param("keyId") Long keyId,
                                        @Param("userId") Long userId,
                                        @Param("userName") String userName,
                                        @Param("keyName") String keyName,
                                        @Param("encrytType") String encrytType,
                                        @Param("encrytName") String encrytName,
                                        @Param("chainHash") String chainHash,
                                        @Param("blockHeight") Long blockHeight,
                                        @Param("remark") String remark);

    /**
     * 删除分发记录
     */
    int deleteKeyDistributeRecordById(Long recordId);
}
