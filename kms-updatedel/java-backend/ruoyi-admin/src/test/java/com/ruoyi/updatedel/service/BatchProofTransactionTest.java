package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.mapper.KeyOperationRecordMapper;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import java.sql.Connection;
import java.util.Arrays;
import java.util.Collections;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class BatchProofTransactionTest {
    @Test void proofGroupsCommitOnceAndRollBackEarlierProofWritesOnFailure() throws Exception {
        for (boolean fail : Arrays.asList(false, true)) {
            KeyOperationRecordMapper records = mock(KeyOperationRecordMapper.class);
            KeyOperationRecord record = new KeyOperationRecord();
            record.setRecordId(1L); record.setNodeIndex(0); record.setExpectedCount(1);
            record.setConsistencyHash(String.join("", Collections.nCopies(64, "a")));
            when(records.selectBatchRecords("first", "UPDATE")).thenReturn(Collections.singletonList(record));
            if (fail) when(records.selectBatchRecords("second", "UPDATE")).thenThrow(new IllegalStateException("offline"));
            else when(records.selectBatchRecords("second", "UPDATE")).thenReturn(Collections.emptyList());
            DataSource source = mock(DataSource.class);
            Connection connection = mock(Connection.class);
            when(source.getConnection()).thenReturn(connection);
            when(connection.getAutoCommit()).thenReturn(true);
            KeyOperationRecordService target = new KeyOperationRecordService(records, mock(KeymanageMapper.class), mock(JdbcTemplate.class));
            ProxyFactory proxy = new ProxyFactory(target);
            proxy.addAdvice(new TransactionInterceptor(new DataSourceTransactionManager(source), new AnnotationTransactionAttributeSource()));
            KeyOperationRecordService service = (KeyOperationRecordService) proxy.getProxy();
            if (fail) {
                assertThrows(IllegalStateException.class, () -> service.refreshBatchProofs(Arrays.asList("first", "second"), "UPDATE"));
                verify(connection).rollback(); verify(connection, never()).commit();
            } else {
                service.refreshBatchProofs(Arrays.asList("first", "second"), "UPDATE");
                verify(connection).commit(); verify(connection, never()).rollback();
            }
            verify(records).updateProofPath(eq(1L), anyString());
            verify(records).updateBatchProof(eq("first"), eq("UPDATE"), anyString(), eq("1"), anyString());
        }
    }
}
