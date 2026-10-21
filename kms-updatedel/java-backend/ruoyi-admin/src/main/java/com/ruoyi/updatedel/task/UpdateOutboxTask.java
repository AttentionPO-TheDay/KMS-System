package com.ruoyi.updatedel.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import com.ruoyi.updatedel.service.LifecycleService;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Database completion never waits for proofs, Kafka acknowledgement or chain confirmation. */
@Component
public class UpdateOutboxTask {
    private static final Logger log = LoggerFactory.getLogger(UpdateOutboxTask.class);
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final KeyOperationRecordService proofs;
    private final KafkaTemplate<String, String> kafka;
    private final LifecycleService lifecycle;
    @Value("${kms.lifecycle.kafka.chain-task-topic:key_chain_task}")
    private String topic;
    @Value("${kms.lifecycle.chain-sync-enabled:true}")
    private boolean chainEnabled;

    public UpdateOutboxTask(JdbcTemplate jdbc, ObjectMapper mapper,
                            KeyOperationRecordService proofs, KafkaTemplate<String, String> kafka,
                            LifecycleService lifecycle) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.proofs = proofs;
        this.kafka = kafka;
        this.lifecycle = lifecycle;
    }

    @Scheduled(fixedDelayString = "${kms.lifecycle.update-outbox-delay-ms:200}")
    public void dispatch() {
        if (lifecycle.hasActiveRotation()) return;
        List<Map<String, Object>> rows = jdbc.queryForList(
            "SELECT id,event_json FROM key_update_outbox ORDER BY id LIMIT 100");
        for (Map<String, Object> row : rows) {
            if (lifecycle.hasActiveRotation()) return;
            try {
                String json = (String) row.get("event_json");
                JsonNode payload = mapper.readTree(json);
                // Older events serialized both the canonical list and its getKeys() alias.
                // Do not let Jackson's setterless alias append the same keys a second time.
                if (payload.isObject() && payload.has("keyList")) ((ObjectNode) payload).remove("keys");
                ChainSyncEvent event = mapper.treeToValue(payload, ChainSyncEvent.class);
                Set<String> batches = new LinkedHashSet<>();
                for (Keymanage key : event.getKeys()) {
                    batches.add(key.getBatchId());
                }
                List<String> batchIds = new java.util.ArrayList<>(batches);
                for (int start = 0; start < batchIds.size(); start += 200) {
                    // Give foreground transactions priority. The durable event remains for retry.
                    if (lifecycle.hasActiveRotation()) return;
                    // Propagate a failed refresh so this durable row is retried next time.
                    proofs.refreshBatchProofs(batchIds.subList(start, Math.min(start + 200, batchIds.size())), "UPDATE");
                }
                if (chainEnabled) {
                    for (int start = 0; start < event.getKeys().size(); start += 200) {
                        sendBounded(event.getActionType(), event.getKeys().subList(start,
                            Math.min(start + 200, event.getKeys().size())));
                    }
                }
                jdbc.update("DELETE FROM key_update_outbox WHERE id=?", row.get("id"));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            } catch (Exception ex) {
                // No key material in logs. At-least-once delivery, retained on any failure.
                log.warn("update follow-up pending, outboxId={}, failure={}", row.get("id"), ex.getClass().getSimpleName());
                return;
            }
        }
    }

    private void sendBounded(String actionType, List<Keymanage> keys) throws Exception {
        ObjectNode payload = mapper.valueToTree(new ChainSyncEvent(actionType, keys));
        payload.remove("keys"); // keyList is the canonical Kafka field; serialize it only once.
        String json = mapper.writeValueAsString(payload);
        if (json.getBytes(StandardCharsets.UTF_8).length > 768 * 1024) {
            if (keys.size() <= 1) throw new IllegalStateException("single chain event exceeds message budget");
            int middle = keys.size() / 2;
            sendBounded(actionType, keys.subList(0, middle));
            sendBounded(actionType, keys.subList(middle, keys.size()));
            return;
        }
        kafka.send(topic, json).get(30, TimeUnit.SECONDS);
    }
}
