package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.KeyOperationRecord;
import java.util.Date;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface KeyOperationRecordMapper {
    int insertKeyOperationRecord(KeyOperationRecord record);

    int insertKeyOperationRecordBatch(@Param("records") List<KeyOperationRecord> records);

    List<KeyOperationRecord> selectKeyOperationRecordList(KeyOperationRecord query);

    int updateLatestResult(@Param("keyId") Long keyId,
                           @Param("actionType") String actionType,
                           @Param("resultStatus") String resultStatus,
                           @Param("chainStatus") String chainStatus,
                           @Param("chainHash") String chainHash,
                           @Param("blockHeight") Long blockHeight,
                           @Param("resultMessage") String resultMessage);

    List<KeyOperationRecord> selectBatchRecords(@Param("batchId") String batchId, @Param("actionType") String actionType);

    int updateBatchProof(@Param("batchId") String batchId,
                         @Param("actionType") String actionType,
                         @Param("batchRoot") String batchRoot,
                         @Param("verifyStatus") String verifyStatus,
                         @Param("verifyMessage") String verifyMessage);

    int markReceived(@Param("recordId") Long recordId, @Param("userId") Long userId);

    KeyOperationRecord selectKeyOperationRecordById(Long recordId);

    int countByActionType(@Param("actionType") String actionType);

    int countPendingReceives();

    int countFailedResults();

    List<KeyOperationRecord> selectRecentRecordsSince(@Param("startTime") Date startTime);
}
