package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.updatedel.domain.AutoUpdateItem;
import com.ruoyi.updatedel.domain.AutoUpdateRun;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.AutoUpdateRecordMapper;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.service.generator.EccKeyGenerator;
import com.ruoyi.updatedel.service.generator.SsclKeyGenerator;
import java.sql.Connection;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;
import java.util.stream.Collectors;
import java.util.stream.LongStream;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AutoUpdateRunServiceTest {
    private AutoUpdateRecordMapper records;
    private KeymanageMapper keys;
    private LifecycleService lifecycle;
    private AutoUpdateRunService service;

    @BeforeEach
    void setUp() {
        records = mock(AutoUpdateRecordMapper.class);
        keys = mock(KeymanageMapper.class);
        lifecycle = mock(LifecycleService.class);
        service = new AutoUpdateRunService(records, keys, lifecycle);
        when(records.insertItems(anyList())).thenAnswer(call -> ((List<?>) call.getArgument(0)).size());
        when(records.selectRunList(any())).thenAnswer(call -> Collections.singletonList(call.getArgument(0)));
    }

    @Test
    @SuppressWarnings("unchecked")
    void realLifecycleTransactionsIsolateFailureAndBackoffPreventsNextWindowRetry() throws Exception {
        Keymanage failed = key(1L, "KYBER-768");
        Keymanage successful = key(2L, "SM2");
        Keymanage waiting = key(3L, "SM2");
        String old = LocalDateTime.now().minusHours(2).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        failed.setUpdTime(old);
        successful.setUpdTime(old);
        waiting.setUpdTime(LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        List<Keymanage> state = new ArrayList<>(Arrays.asList(failed, successful, waiting));
        when(keys.selectAutoUpdateCandidates(anyString())).thenAnswer(call -> {
            String cutoff = call.getArgument(0);
            return state.stream().filter(k -> k.getUpdTime().compareTo(cutoff) <= 0).collect(Collectors.toList());
        });
        when(keys.selectkeymanageByKeyId(anyLong())).thenAnswer(call -> state.stream()
            .filter(k -> k.getKeyId().equals(call.getArgument(0))).findFirst().orElse(null));
        when(keys.updatekeymanage(any())).thenAnswer(call -> {
            Keymanage next = call.getArgument(0);
            state.set(1, next);
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            return 1;
        });
        when(keys.touchUpdTime(eq(1L), anyString())).thenAnswer(call -> {
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive(), "backoff must survive rotation rollback");
            failed.setUpdTime(call.getArgument(1));
            return 1;
        });
        when(keys.countAutoUpdateEnabled()).thenReturn(3);
        when(records.insertRun(any())).thenAnswer(call -> {
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive(), "run must not share rotation transaction");
            return 1;
        });
        EccKeyGenerator generator = mock(EccKeyGenerator.class);
        when(generator.generate(anyString(), anyString())).thenReturn("new-material");
        LifecycleService target = new LifecycleService(keys, generator, mock(SsclKeyGenerator.class),
            (KafkaTemplate<String, String>) mock(KafkaTemplate.class), new ObjectMapper(),
            mock(KeyOperationRecordService.class), mock(JdbcTemplate.class));
        ReflectionTestUtils.setField(target, "autoUpdateIntervalMinutes", 30L);

        // Real Spring transaction interception + JDBC transaction manager; only JDBC I/O is mocked.
        DataSource dataSource = mock(DataSource.class);
        Connection failedConnection = mock(Connection.class);
        Connection successfulConnection = mock(Connection.class);
        when(dataSource.getConnection()).thenReturn(failedConnection, successfulConnection);
        when(failedConnection.getAutoCommit()).thenReturn(true);
        when(successfulConnection.getAutoCommit()).thenReturn(true);
        DataSourceTransactionManager manager = new DataSourceTransactionManager(dataSource);
        ProxyFactory lifecycleProxy = new ProxyFactory(target);
        lifecycleProxy.addAdvice(new TransactionInterceptor(manager, new AnnotationTransactionAttributeSource()));
        AutoUpdateRunService executor = new AutoUpdateRunService(records, keys, (LifecycleService) lifecycleProxy.getProxy());
        ProxyFactory runProxy = new ProxyFactory(executor);
        runProxy.addAdvice(new TransactionInterceptor(manager, new AnnotationTransactionAttributeSource()));
        AutoUpdateRunService transactionalExecutor = (AutoUpdateRunService) runProxy.getProxy();

        Object originalSecrets = ReflectionTestUtils.getField(KgcMasterSecret.class, "secrets");
        Object originalActiveId = ReflectionTestUtils.getField(KgcMasterSecret.class, "activeId");
        try {
            // Test-only fixture; this test must not depend on KGC_MASTER_SECRET.
            ReflectionTestUtils.setField(KgcMasterSecret.class, "secrets", Collections.singletonMap(
                "auto-update-test", String.join("", Collections.nCopies(64, "A"))));
            ReflectionTestUtils.setField(KgcMasterSecret.class, "activeId", "auto-update-test");
            transactionalExecutor.executeOnce("MANUAL");
            transactionalExecutor.executeOnce("SCHEDULED");
        } finally {
            ReflectionTestUtils.setField(KgcMasterSecret.class, "secrets", originalSecrets);
            ReflectionTestUtils.setField(KgcMasterSecret.class, "activeId", originalActiveId);
        }

        verify(failedConnection).rollback();
        verify(failedConnection, never()).commit();
        verify(successfulConnection).commit();
        verify(successfulConnection, never()).rollback();
        verify(dataSource, times(2)).getConnection();
        verify(keys).touchUpdTime(eq(1L), anyString());
        verify(keys).archiveCurrentVersion(2L, "ROTATE", "AUTO");
        assertEquals(2, state.get(1).getVersion());
        ArgumentCaptor<List<AutoUpdateItem>> saved = ArgumentCaptor.forClass(List.class);
        verify(records).insertItems(saved.capture());
        assertEquals(2, saved.getValue().size(), "second polling window must add no duplicate items");
        assertEquals("FAILED", saved.getValue().get(0).getResult());
        assertTrue(saved.getValue().get(0).getReason().contains("KYBER"));
        assertNull(saved.getValue().get(0).getToVersion());
        assertEquals("SUCCESS", saved.getValue().get(1).getResult());
        assertEquals(1, saved.getValue().get(1).getFromVersion());
        assertEquals(2, saved.getValue().get(1).getToVersion());
        InOrder order = inOrder(records);
        order.verify(records).insertRun(any());
        order.verify(records).insertItems(anyList());
        order.verify(records).finishRun(anyString(), any(), eq(2), eq(1), eq(1), eq(1));
        order.verify(records).selectRunList(any());
        order.verify(records).insertRun(any());
        order.verify(records).finishRun(anyString(), any(), eq(0), eq(0), eq(0), eq(3));
        assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
    }

    @Test
    void concurrentManualAndScheduledExecutionDoNotSelectOrRotateTheSameCandidate() throws Exception {
        CountDownLatch firstEntered = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        AtomicInteger queries = new AtomicInteger();
        Keymanage candidate = key(5L, "SM2");
        when(lifecycle.listAutoUpdateCandidates()).thenAnswer(call -> {
            if (queries.incrementAndGet() == 1) {
                firstEntered.countDown();
                assertTrue(releaseFirst.await(5, TimeUnit.SECONDS));
                return Collections.singletonList(candidate);
            }
            return Collections.emptyList();
        });
        when(lifecycle.rotateKey(candidate, "AUTO")).thenReturn(candidate);
        FutureTask<AutoUpdateRun> manual = new FutureTask<>(() -> service.executeOnce("MANUAL"));
        FutureTask<AutoUpdateRun> scheduled = new FutureTask<>(() -> {
            secondStarted.countDown();
            return service.executeOnce("SCHEDULED");
        });
        Thread first = new Thread(manual, "manual-auto-update-test");
        Thread second = new Thread(scheduled, "scheduled-auto-update-test");
        try {
            first.start();
            assertTrue(firstEntered.await(3, TimeUnit.SECONDS));
            second.start();
            assertTrue(secondStarted.await(3, TimeUnit.SECONDS));
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
            while (second.getState() != Thread.State.BLOCKED && System.nanoTime() < deadline) {
                LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(1));
            }
            assertEquals(Thread.State.BLOCKED, second.getState(), "second execution must wait on service monitor");
            assertEquals(1, queries.get());
            verify(records, times(1)).insertRun(any());
            releaseFirst.countDown();
            AutoUpdateRun firstRun = manual.get(5, TimeUnit.SECONDS);
            AutoUpdateRun secondRun = scheduled.get(5, TimeUnit.SECONDS);
            assertNotEquals(firstRun.getRunId(), secondRun.getRunId());
            assertEquals("MANUAL", firstRun.getTriggerSource());
            assertEquals("SCHEDULED", secondRun.getTriggerSource());
            verify(lifecycle, times(1)).rotateKey(candidate, "AUTO");
            assertEquals(2, queries.get());
        } finally {
            releaseFirst.countDown();
            first.join(5000);
            second.join(5000);
        }
    }

    @Test
    void backoffWriteFailureDoesNotPreventRemainingCandidatesAndFailureReasonIsBounded() {
        Keymanage failed = key(1L, "FALCON");
        Keymanage next = key(2L, "SM2");
        when(lifecycle.listAutoUpdateCandidates()).thenReturn(Arrays.asList(failed, next));
        when(lifecycle.rotateKey(failed, "AUTO")).thenThrow(new IllegalStateException(String.join("", Collections.nCopies(600, "x"))));
        doThrow(new IllegalStateException("backoff unavailable")).when(lifecycle).backoffAutoUpdateFailure(1L);
        when(lifecycle.rotateKey(next, "AUTO")).thenReturn(next);
        when(keys.countAutoUpdateEnabled()).thenReturn(0);
        service.executeOnce("MANUAL");
        verify(lifecycle).rotateKey(next, "AUTO");
        verify(records).finishRun(anyString(), any(), eq(2), eq(1), eq(1), eq(0));
        verify(records).insertItems(argThat(items -> items.size() == 2
            && items.get(0).getReason().length() <= 500 && items.get(0).getReason().endsWith("...(截断)")));
    }

    @Test
    void laterChunkInsertFailureLeavesRunUnfinishedWithoutUndoingRotations() {
        List<Keymanage> candidates = LongStream.rangeClosed(1, 501).mapToObj(id -> key(id, "SM2")).collect(Collectors.toList());
        when(lifecycle.listAutoUpdateCandidates()).thenReturn(candidates);
        when(lifecycle.rotateKey(any(), eq("AUTO"))).thenAnswer(call -> call.getArgument(0));
        IllegalStateException failure = new IllegalStateException("item storage unavailable");
        when(records.insertItems(anyList())).thenReturn(500).thenThrow(failure);
        assertSame(failure, assertThrows(IllegalStateException.class, () -> service.executeOnce("MANUAL")));
        verify(lifecycle, times(501)).rotateKey(any(), eq("AUTO"));
        verify(records).insertItems(argThat(items -> items.size() == 500));
        verify(records).insertItems(argThat(items -> items.size() == 1));
        verify(records, never()).finishRun(anyString(), any(), anyInt(), anyInt(), anyInt(), anyInt());
        verify(records, never()).selectRunList(any());
        verify(records).insertRun(argThat(run -> run.getFinishedAt() == null));
    }

    @Test
    void shortItemWriteAlsoCannotPublishCompletion() {
        Keymanage candidate = key(1L, "SM2");
        when(lifecycle.listAutoUpdateCandidates()).thenReturn(Collections.singletonList(candidate));
        when(lifecycle.rotateKey(candidate, "AUTO")).thenReturn(candidate);
        when(records.insertItems(anyList())).thenReturn(0);
        assertThrows(IllegalStateException.class, () -> service.executeOnce("MANUAL"));
        verify(records, never()).finishRun(anyString(), any(), anyInt(), anyInt(), anyInt(), anyInt());
    }

    @Test
    void latestQueriesIgnoreNullsAndDeduplicateBeforeApplyingTwoHundredKeyCap() {
        List<Long> request = new ArrayList<>(Arrays.asList(null, 1L, 1L));
        LongStream.rangeClosed(2, 205).forEach(request::add);
        service.latestByKeyIds(null, 42L);
        service.latestByKeyIds(Collections.emptyList(), 42L);
        service.latestByKeyIds(Arrays.asList(null, null), 42L);
        verifyNoInteractions(records);
        service.latestByKeyIds(request, 42L);
        verify(records).selectLatestItemsByKeyIds(argThat(ids -> ids.size() == 200
            && ids.get(0) == 1L && ids.get(199) == 200L), eq(42L));
    }

    private Keymanage key(long id, String algorithm) {
        Keymanage key = new Keymanage();
        key.setKeyId(id);
        key.setUserId(42L);
        key.setUserName("owner");
        key.setKeyName("key-" + id);
        key.setEncrytName(algorithm);
        key.setUa("existing-user-share");
        key.setKeyValue("old-material");
        key.setVersion(1);
        key.setStatus("0");
        key.setAutoUpdate("1");
        return key;
    }
}
