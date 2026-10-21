package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.service.generator.EccKeyGenerator;
import com.ruoyi.updatedel.service.generator.SsclKeyGenerator;
import java.sql.Connection;
import java.util.Collections;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class RotationBatchTest {
    @Test void outboxFailureRollsBackKeyHistoryAndAuditWithoutCallingChain() throws Exception {
        KeymanageMapper keys = mock(KeymanageMapper.class);
        EccKeyGenerator generator = mock(EccKeyGenerator.class);
        KeyOperationRecordService audit = mock(KeyOperationRecordService.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        KafkaTemplate kafka = mock(KafkaTemplate.class);
        LifecycleService target = new LifecycleService(keys, generator, mock(SsclKeyGenerator.class), kafka, new ObjectMapper(), audit, jdbc);
        DataSource source = mock(DataSource.class);
        Connection connection = mock(Connection.class);
        when(source.getConnection()).thenReturn(connection);
        when(connection.getAutoCommit()).thenReturn(true);
        ProxyFactory proxy = new ProxyFactory(target);
        proxy.addAdvice(new TransactionInterceptor(new DataSourceTransactionManager(source), new AnnotationTransactionAttributeSource()));
        LifecycleService service = (LifecycleService) proxy.getProxy();
        Keymanage old = new Keymanage(); old.setKeyId(1L); old.setUserName("acceptance_user");
        old.setUa("public-ua"); old.setEncrytName("SM2"); old.setStatus("0"); old.setVersion(1);
        when(keys.selectRotationCandidates(eq("acceptance_user"), anyList())).thenReturn(Collections.singletonList(old));
        when(generator.generate(anyString(), anyString())).thenReturn("new-material");
        when(jdbc.update(startsWith("update keymanage k join"), org.mockito.ArgumentMatchers.<Object[]>any())).thenReturn(1);
        when(jdbc.update(startsWith("INSERT INTO key_update_outbox"), any(Object.class)))
            .thenAnswer(call -> {
                com.fasterxml.jackson.databind.JsonNode event = new ObjectMapper().readTree((String) call.getArgument(1));
                assertFalse(event.has("keys"));
                assertEquals(1, event.get("keyList").size());
                throw new IllegalStateException("outbox write failed");
            });
        Keymanage request = new Keymanage(); request.setKeyId(1L);
        Object originalSecrets = ReflectionTestUtils.getField(KgcMasterSecret.class, "secrets");
        Object originalId = ReflectionTestUtils.getField(KgcMasterSecret.class, "activeId");
        try {
            ReflectionTestUtils.setField(KgcMasterSecret.class, "secrets", Collections.singletonMap("test", String.join("", Collections.nCopies(64, "A"))));
            ReflectionTestUtils.setField(KgcMasterSecret.class, "activeId", "test");
            assertThrows(IllegalStateException.class, () -> service.rotateKeys("acceptance_user", Collections.singletonList(request)));
        } finally {
            ReflectionTestUtils.setField(KgcMasterSecret.class, "secrets", originalSecrets);
            ReflectionTestUtils.setField(KgcMasterSecret.class, "activeId", originalId);
        }
        verify(connection).rollback(); verify(connection, never()).commit();
        assertFalse(service.hasActiveRotation(), "rollback must release background dispatch");
        org.mockito.InOrder order = inOrder(keys, audit, jdbc);
        order.verify(keys).selectRotationCandidates(eq("acceptance_user"), anyList());
        order.verify(keys).archiveRotationBatch(anyList());
        order.verify(jdbc).update(startsWith("update keymanage k join"), org.mockito.ArgumentMatchers.<Object[]>any());
        order.verify(audit).createPendingRecords(anyList(), eq("UPDATE"), eq("MANUAL"), anyString());
        order.verify(jdbc).update(startsWith("INSERT INTO key_update_outbox"), any(Object.class));
        verifyNoInteractions(kafka);
    }

    @Test void foreignOrMissingKeysAreRejectedBeforeAnyWrites() {
        KeymanageMapper keys = mock(KeymanageMapper.class);
        when(keys.selectRotationCandidates(anyString(), anyList())).thenReturn(Collections.emptyList());
        LifecycleService service = new LifecycleService(keys, null, null, null, null, null, null);
        Keymanage request = new Keymanage(); request.setKeyId(9L);
        assertThrows(IllegalStateException.class, () -> service.rotateKeys("alice", Collections.singletonList(request)));
        verify(keys, never()).archiveRotationBatch(anyList());
        verify(keys, never()).updatekeymanage(any());
    }
}
