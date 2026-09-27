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

    /**
     * 写入单条记录的 Merkle 证明路径。
     *
     * @param recordId  记录主键
     * @param proofPath 以 {@code |} 分隔的证明路径
     * @return 影响行数
     */
    int updateProofPath(@Param("recordId") Long recordId, @Param("proofPath") String proofPath);

    int markReceived(@Param("recordId") Long recordId, @Param("userId") Long userId);

    KeyOperationRecord selectKeyOperationRecordById(Long recordId);

    int countByActionType(@Param("actionType") String actionType);

    int countPendingReceives();

    int countFailedResults();

    List<KeyOperationRecord> selectRecentDashboardRecordsSince(@Param("startTime") Date startTime);

    List<KeyOperationRecord> selectRecentRecordsSince(@Param("startTime") Date startTime);
}
