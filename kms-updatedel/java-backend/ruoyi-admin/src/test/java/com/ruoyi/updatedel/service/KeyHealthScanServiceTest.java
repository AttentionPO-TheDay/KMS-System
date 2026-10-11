package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.KeyHealthResult;
import com.ruoyi.updatedel.domain.KeyHealthScanItem;
import com.ruoyi.updatedel.domain.KeyHealthScanRun;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeyHealthScanMapper;
import com.ruoyi.updatedel.mapper.KeyOperationRecordMapper;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.LongStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class KeyHealthScanServiceTest {
    private KeyHealthScanMapper records;
    private KeymanageMapper keys;
    private KeyHealthService health;
    private KeyHealthScanService service;
    private List<Keymanage> targets;

    @BeforeEach
    void setUp() {
        records = mock(KeyHealthScanMapper.class);
        keys = mock(KeymanageMapper.class);
        health = mock(KeyHealthService.class);
        service = new KeyHealthScanService(records, keys, health);
        ReflectionTestUtils.setField(service, "maxKeysPerScan", 2000);
        targets = new ArrayList<>();
        when(keys.selectScanTargets(nullable(Long.class), anyLong(), anyInt())).thenAnswer(call -> {
            Long owner = call.getArgument(0);
            long after = call.getArgument(1);
            int limit = call.getArgument(2);
            return targets.stream().filter(k -> k.getKeyId() > after
                && (owner == null || owner.equals(k.getUserId()))).limit(limit).collect(Collectors.toList());
        });
        when(keys.countScanTargetsAfter(nullable(Long.class), anyLong())).thenAnswer(call -> {
            Long owner = call.getArgument(0);
            long after = call.getArgument(1);
            return (int) targets.stream().filter(k -> k.getKeyId() > after
                && (owner == null || owner.equals(k.getUserId()))).count();
        });
        when(health.check(anyLong())).thenAnswer(call -> result());
        when(records.insertItems(anyList())).thenAnswer(call -> ((List<?>) call.getArgument(0)).size());
    }

    @Test
    @SuppressWarnings("unchecked")
    void realSingleKeyRulesAggregateIntoMatchingPersistedCounters() {
        Keymanage ok = key(10L, 42L);
        Keymanage warning = key(20L, 42L);
        warning.setUa(null);
        Keymanage error = key(30L, 42L);
        error.setUa(null);
        error.setKeyValue(null);
        Keymanage revoked = key(40L, 42L);
        revoked.setStatus("3");
        targets.addAll(Arrays.asList(ok, warning, error, revoked));
        when(keys.selectkeymanageByKeyId(anyLong())).thenAnswer(call -> targets.stream()
            .filter(k -> k.getKeyId().equals(call.getArgument(0))).findFirst().orElse(null));
        KeyOperationRecordMapper operations = mock(KeyOperationRecordMapper.class);
        when(operations.selectKeyOperationRecordList(any())).thenReturn(Collections.emptyList());
        KeyHealthService realHealth = new KeyHealthService();
        ReflectionTestUtils.setField(realHealth, "keymanageMapper", keys);
        ReflectionTestUtils.setField(realHealth, "keyOperationRecordMapper", operations);
        service = new KeyHealthScanService(records, keys, realHealth);
        ReflectionTestUtils.setField(service, "maxKeysPerScan", 2000);

        KeyHealthScanRun run = service.scan(42L);
        assertEquals(4, run.getTotal());
        assertEquals(2, run.getOkCount());
        assertEquals(1, run.getWarnCount());
        assertEquals(1, run.getErrorCount());
        assertEquals("OWNER", run.getScope());
        assertEquals(42L, run.getUserId());
        assertNotNull(run.getFinishedAt());
        assertNull(run.getNote());
        ArgumentCaptor<List<KeyHealthScanItem>> saved = ArgumentCaptor.forClass(List.class);
        verify(records).insertItems(saved.capture());
        List<KeyHealthScanItem> items = saved.getValue();
        assertEquals(run.getTotal().intValue(), items.size());
        assertEquals(Arrays.asList("OK", "WARN", "ERROR", "OK"), items.stream()
            .map(KeyHealthScanItem::getVerdict).collect(Collectors.toList()));
        assertEquals("ua-missing", items.get(1).getRule());
        assertEquals("material-missing", items.get(2).getRule());
        assertTrue(items.get(3).getSummary().contains("已回收（终态）"));
        for (KeyHealthScanItem item : items) {
            assertEquals(run.getRunId(), item.getRunId());
            assertEquals(42L, item.getUserId());
        }
        InOrder order = inOrder(records);
        order.verify(records).insertRun(any());
        order.verify(records).insertItems(anyList());
        order.verify(records).finishRun(eq(run.getRunId()), eq(run.getFinishedAt()), eq(4), eq(2), eq(1), eq(1), isNull());
    }

    @Test
    @SuppressWarnings("unchecked")
    void errorSeverityWinsRegardlessOfOrderAndRulesAreDeduplicated() {
        targets.add(key(10L, 42L));
        KeyHealthResult finding = result();
        finding.setVersion(7);
        finding.setHealth(KeyHealthResult.OK);
        finding.setFindings(Arrays.asList(
            new KeyHealthResult.Finding("same-rule", "WARN", "first warning", ""),
            new KeyHealthResult.Finding("fatal-rule", "ERROR", "fatal issue", ""),
            new KeyHealthResult.Finding("same-rule", "WARN", "second warning", ""),
            new KeyHealthResult.Finding("info-rule", "INFO", "observation", "")));
        when(health.check(10L)).thenReturn(finding);
        KeyHealthScanRun run = service.scan(null);
        assertEquals("ALL", run.getScope());
        assertEquals(0, run.getOkCount());
        assertEquals(0, run.getWarnCount());
        assertEquals(1, run.getErrorCount());
        ArgumentCaptor<List<KeyHealthScanItem>> saved = ArgumentCaptor.forClass(List.class);
        verify(records).insertItems(saved.capture());
        KeyHealthScanItem item = saved.getValue().get(0);
        assertEquals("ERROR", item.getVerdict());
        assertEquals("same-rule,fatal-rule,info-rule", item.getRule());
        assertEquals(7, item.getKeyVersion());
        assertTrue(item.getSummary().contains("fatal issue"));
    }

    @Test
    void missingFindingMessageRetainsRuleAndDoesNotClaimNoIssues() {
        targets.add(key(10L, 42L));
        KeyHealthResult result = result();
        result.warn("only-rule", " ", "");
        when(health.check(10L)).thenReturn(result);
        service.scan(null);
        verify(records).insertItems(argThat(items -> "WARN".equals(items.get(0).getVerdict())
            && "only-rule".equals(items.get(0).getRule())
            && items.get(0).getSummary().contains("未提供问题说明")
            && !items.get(0).getSummary().contains("未发现")));
    }

    @Test
    void deletionRaceAdvancesKeysetAndDoesNotConsumeVerdictCap() {
        addTargets(501);
        ReflectionTestUtils.setField(service, "maxKeysPerScan", 1);
        when(health.check(anyLong())).thenAnswer(call -> (Long) call.getArgument(0) <= 5000L ? null : result());
        KeyHealthScanRun run = service.scan(42L);
        assertEquals(1, run.getTotal());
        assertEquals(1, run.getOkCount());
        assertEquals(0, run.getWarnCount());
        assertEquals(0, run.getErrorCount());
        assertTrue(run.getNote().contains("500 把密钥被删除"));
        assertFalse(run.getNote().contains("达到单次扫描上限"));
        verify(keys).selectScanTargets(42L, 0L, 500);
        verify(keys).selectScanTargets(42L, 5000L, 500);
        verify(records).insertItems(argThat(items -> items.size() == 1 && items.get(0).getKeyId() == 5010L));
    }

    @ParameterizedTest
    @ValueSource(ints = {499, 500, 501})
    void exactCapAndSparseKeysetBoundariesDoNotReportFalseTruncation(int total) {
        addTargets(total);
        // An unrelated owner after the last key must not produce a false remaining count.
        targets.add(key(90000L, 43L));
        ReflectionTestUtils.setField(service, "maxKeysPerScan", total);
        KeyHealthScanRun run = service.scan(42L);
        assertEquals(total, run.getTotal());
        assertEquals(total, run.getOkCount());
        assertNull(run.getNote());
        verify(health, times(total)).check(anyLong());
        verify(health, never()).check(90000L);
        verify(keys, never()).countScanTargetsAfter(nullable(Long.class), anyLong());
        if (total >= 500) {
            verify(keys).selectScanTargets(42L, 5000L, 500);
        }
        verify(records).finishRun(anyString(), any(), eq(total), eq(total), eq(0), eq(0), isNull());
    }

    @Test
    void cappedScanReportsExactOwnerScopedRemainderAndPersistsAllChunksBeforeFinishing() {
        addTargets(503);
        targets.add(key(90000L, 43L));
        ReflectionTestUtils.setField(service, "maxKeysPerScan", 501);
        KeyHealthScanRun run = service.scan(42L);
        assertEquals(501, run.getTotal());
        assertTrue(run.getNote().contains("上限 501 条，剩余 2 把未扫描"));
        verify(keys).countScanTargetsAfter(42L, 5010L);
        verify(health, never()).check(5020L);
        verify(health, never()).check(5030L);
        InOrder order = inOrder(records);
        order.verify(records).insertRun(any());
        order.verify(records).insertItems(argThat(items -> items.size() == 500));
        order.verify(records).insertItems(argThat(items -> items.size() == 1));
        order.verify(records).finishRun(anyString(), any(), eq(501), eq(501), eq(0), eq(0), eq(run.getNote()));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, -7})
    void nonPositiveConfiguredCapUsesAndReportsEffectiveDefault(int configured) {
        addTargets(2001);
        ReflectionTestUtils.setField(service, "maxKeysPerScan", configured);
        KeyHealthScanRun run = service.scan(null);
        assertEquals(2000, run.getTotal());
        assertTrue(run.getNote().contains("上限 2000 条，剩余 1 把未扫描"));
        verify(keys).countScanTargetsAfter(null, 20000L);
        verify(health, never()).check(20010L);
    }

    @Test
    void laterItemChunkFailureLeavesPersistedRunUnfinishedAndPropagatesError() {
        addTargets(501);
        IllegalStateException failure = new IllegalStateException("scan storage unavailable");
        when(records.insertItems(anyList())).thenReturn(500).thenThrow(failure);
        assertSame(failure, assertThrows(IllegalStateException.class, () -> service.scan(null)));
        verify(records).insertItems(argThat(items -> items.size() == 500));
        verify(records).insertItems(argThat(items -> items.size() == 1));
        verify(records, never()).finishRun(anyString(), any(), anyInt(), anyInt(), anyInt(), anyInt(), nullable(String.class));
        verify(records).insertRun(argThat(run -> run.getFinishedAt() == null));
    }

    @Test
    void shortItemWriteDoesNotPublishCompletion() {
        targets.add(key(10L, 42L));
        when(records.insertItems(anyList())).thenReturn(0);
        assertThrows(IllegalStateException.class, () -> service.scan(null));
        verify(records, never()).finishRun(anyString(), any(), anyInt(), anyInt(), anyInt(), anyInt(), nullable(String.class));
    }

    @Test
    void emptyScanCompletesWithoutIssuingAnEmptyInsert() {
        when(keys.selectScanTargets(null, 0L, 500)).thenReturn(null);
        KeyHealthScanRun run = service.scan(null);
        assertEquals(0, run.getTotal());
        assertEquals(0, run.getOkCount());
        assertEquals(0, run.getWarnCount());
        assertEquals(0, run.getErrorCount());
        assertNull(run.getNote());
        assertNotNull(run.getFinishedAt());
        verify(records, never()).insertItems(anyList());
        verify(records).finishRun(eq(run.getRunId()), eq(run.getFinishedAt()), eq(0), eq(0), eq(0), eq(0), isNull());
        verifyNoInteractions(health);
    }

    private void addTargets(int count) {
        LongStream.rangeClosed(1, count).forEach(id -> targets.add(key(id * 10, 42L)));
    }

    private Keymanage key(long id, long owner) {
        Keymanage key = new Keymanage();
        key.setKeyId(id);
        key.setUserId(owner);
        key.setUserName("owner-" + owner);
        key.setKeyName("key-" + id);
        key.setEncrytName("SM2");
        key.setVersion(1);
        key.setStatus("0");
        key.setUa("user-share");
        key.setKeyValue("kgc-share");
        return key;
    }

    private KeyHealthResult result() {
        return new KeyHealthResult();
    }
}
