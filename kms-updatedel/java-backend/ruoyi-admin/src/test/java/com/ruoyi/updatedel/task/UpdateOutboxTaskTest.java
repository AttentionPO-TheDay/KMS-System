package com.ruoyi.updatedel.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import com.ruoyi.updatedel.service.LifecycleService;
import java.util.Collections;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.util.concurrent.SettableListenableFuture;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class UpdateOutboxTaskTest {
    @Test void legacyDuplicateAliasAndLargeUtf8EventsAreSplitWithoutLosingKeys() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        KeyOperationRecordService proofs = mock(KeyOperationRecordService.class);
        KafkaTemplate kafka = mock(KafkaTemplate.class);
        ObjectMapper mapper = new ObjectMapper();
        ArrayList<Keymanage> keys = new ArrayList<>();
        for (long id = 1; id <= 3; id++) {
            Keymanage key = new Keymanage(); key.setKeyId(id); key.setBatchId("batch");
            key.setKeyValue(String.join("", Collections.nCopies(150000, "测")));
            keys.add(key);
        }
        Map<String, Object> row = new LinkedHashMap<>(); row.put("id", 1L);
        row.put("event_json", mapper.writeValueAsString(new ChainSyncEvent(ChainSyncEvent.TYPE_KEY_UPDATED, keys)));
        when(jdbc.queryForList(anyString())).thenReturn(Collections.singletonList(row));
        Set<Long> seen = new HashSet<>();
        when(kafka.send(eq("chain"), anyString())).thenAnswer(call -> {
            String json = call.getArgument(1);
            assertTrue(json.getBytes(StandardCharsets.UTF_8).length <= 768 * 1024);
            assertFalse(mapper.readTree(json).has("keys"));
            ChainSyncEvent event = mapper.readValue(json, ChainSyncEvent.class);
            for (Keymanage key : event.getKeys()) assertTrue(seen.add(key.getKeyId()));
            SettableListenableFuture success = new SettableListenableFuture(); success.set(null); return success;
        });
        UpdateOutboxTask task = new UpdateOutboxTask(jdbc, mapper, proofs, kafka, mock(LifecycleService.class));
        ReflectionTestUtils.setField(task, "topic", "chain");
        ReflectionTestUtils.setField(task, "chainEnabled", true);
        task.dispatch();
        assertEquals(new HashSet<>(java.util.Arrays.asList(1L, 2L, 3L)), seen);
        verify(kafka, times(3)).send(eq("chain"), anyString());
        verify(jdbc).update("DELETE FROM key_update_outbox WHERE id=?", 1L);
    }

    @Test void foregroundRotationDefersDurableWorkAndIdleDispatchResumes() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        KeyOperationRecordService proofs = mock(KeyOperationRecordService.class);
        KafkaTemplate kafka = mock(KafkaTemplate.class);
        LifecycleService lifecycle = mock(LifecycleService.class);
        UpdateOutboxTask task = fixture(jdbc, proofs, kafka, lifecycle);
        when(lifecycle.hasActiveRotation()).thenReturn(true);
        task.dispatch();
        verify(jdbc, never()).queryForList(anyString());
        verifyNoInteractions(proofs, kafka);
        when(lifecycle.hasActiveRotation()).thenReturn(false);
        task.dispatch();
        verify(proofs).refreshBatchProofs(Collections.singletonList("batch"), "UPDATE");
        verify(jdbc).update("DELETE FROM key_update_outbox WHERE id=?", 1L);
    }

    @Test void proofFailureKeepsDurableWorkAndNeverSendsChainTask() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        KeyOperationRecordService proofs = mock(KeyOperationRecordService.class);
        KafkaTemplate kafka = mock(KafkaTemplate.class);
        UpdateOutboxTask task = fixture(jdbc, proofs, kafka);
        doThrow(new IllegalStateException("database unavailable")).when(proofs).refreshBatchProofs(Collections.singletonList("batch"), "UPDATE");
        task.dispatch();
        verify(jdbc, never()).update(anyString(), any(Object.class));
        verifyNoInteractions(kafka);
    }

    @Test void kafkaFailureRetainsWorkAndNextDispatchRetries() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        KeyOperationRecordService proofs = mock(KeyOperationRecordService.class);
        KafkaTemplate kafka = mock(KafkaTemplate.class);
        UpdateOutboxTask task = fixture(jdbc, proofs, kafka);
        ReflectionTestUtils.setField(task, "chainEnabled", true);
        SettableListenableFuture failed = new SettableListenableFuture();
        failed.setException(new IllegalStateException("offline"));
        SettableListenableFuture success = new SettableListenableFuture();
        success.set(null);
        when(kafka.send(eq("chain"), anyString())).thenReturn(failed, success);
        task.dispatch();
        verify(jdbc, never()).update(anyString(), any(Object.class));
        task.dispatch();
        verify(jdbc).update("DELETE FROM key_update_outbox WHERE id=?", 1L);
        verify(proofs, times(2)).refreshBatchProofs(Collections.singletonList("batch"), "UPDATE");
    }

    @Test void disabledChainStillFinishesProofWithoutSending() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        KeyOperationRecordService proofs = mock(KeyOperationRecordService.class);
        KafkaTemplate kafka = mock(KafkaTemplate.class);
        fixture(jdbc, proofs, kafka).dispatch();
        verify(proofs).refreshBatchProofs(Collections.singletonList("batch"), "UPDATE");
        verify(jdbc).update("DELETE FROM key_update_outbox WHERE id=?", 1L);
        verifyNoInteractions(kafka);
    }

    private UpdateOutboxTask fixture(JdbcTemplate jdbc, KeyOperationRecordService proofs, KafkaTemplate kafka) throws Exception {
        return fixture(jdbc, proofs, kafka, mock(LifecycleService.class));
    }

    private UpdateOutboxTask fixture(JdbcTemplate jdbc, KeyOperationRecordService proofs, KafkaTemplate kafka,
                                     LifecycleService lifecycle) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        Keymanage key = new Keymanage(); key.setKeyId(3L); key.setBatchId("batch");
        Map<String, Object> row = new LinkedHashMap<>(); row.put("id", 1L);
        row.put("event_json", mapper.writeValueAsString(new ChainSyncEvent(ChainSyncEvent.TYPE_KEY_UPDATED, Collections.singletonList(key))));
        when(jdbc.queryForList(anyString())).thenReturn(Collections.singletonList(row));
        UpdateOutboxTask task = new UpdateOutboxTask(jdbc, mapper, proofs, kafka, lifecycle);
        ReflectionTestUtils.setField(task, "topic", "chain");
        return task;
    }
}
