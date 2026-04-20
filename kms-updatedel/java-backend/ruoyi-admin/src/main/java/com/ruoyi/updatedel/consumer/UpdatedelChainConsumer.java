package com.ruoyi.updatedel.consumer;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.UpdatedelChainService;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import javax.annotation.PreDestroy;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "kms.lifecycle.chain-consumer-enabled", havingValue = "true", matchIfMissing = true)
public class UpdatedelChainConsumer {

    private static final Logger log = LoggerFactory.getLogger(UpdatedelChainConsumer.class);

    private final UpdatedelChainService updatedelChainService;
    private final ExecutorService chainExecutor;
    private final int chainBatchSize;
    private final int failureSampleSize;

    public UpdatedelChainConsumer(UpdatedelChainService updatedelChainService,
                                  @Value("${kms.lifecycle.chain-worker-threads:4}") int chainWorkerThreads,
                                  @Value("${kms.lifecycle.chain-batch-size:20}") int chainBatchSize,
                                  @Value("${kms.lifecycle.chain-failure-sample-size:5}") int failureSampleSize) {
        this.updatedelChainService = updatedelChainService;
        this.chainExecutor = Executors.newFixedThreadPool(effectivePositive(chainWorkerThreads, 4), new ThreadFactory() {
            private final AtomicInteger counter = new AtomicInteger(1);

            @Override
            public Thread newThread(Runnable runnable) {
                Thread thread = new Thread(runnable, "updatedel-chain-worker-" + counter.getAndIncrement());
                thread.setDaemon(true);
                return thread;
            }
        });
        this.chainBatchSize = effectivePositive(chainBatchSize, 20);
        this.failureSampleSize = effectivePositive(failureSampleSize, 5);
    }

    @KafkaListener(
        topics = "${kms.lifecycle.kafka.chain-task-topic:key_chain_task}",
        groupId = "kms-updatedel-chain-consumer-group",
        concurrency = "${kms.lifecycle.chain-consumer-concurrency:2}",
        properties = {
            "max.poll.records=${kms.lifecycle.chain-max-poll-records:10}",
            "max.poll.interval.ms=${kms.lifecycle.chain-max-poll-interval-ms:900000}"
        }
    )
    public void onMessage(List<ConsumerRecord<String, String>> records) {
        int taskCount = 0;
        for (ConsumerRecord<String, String> record : records) {
            try {
                ChainSyncEvent event = parseEvent(record);
                if (event == null || event.getKeys() == null || event.getKeys().isEmpty()) {
                    continue;
                }

                String actionType = event.getActionType();
                if (ChainSyncEvent.TYPE_ROTATE.equals(actionType) || ChainSyncEvent.TYPE_REVOKE.equals(actionType)) {
                    taskCount += handleKeys(actionType, event.getKeys());
                } else {
                    log.debug("UpdatedelChainConsumer ignored actionType={}", actionType);
                }
            } catch (Exception e) {
                log.error("UpdatedelChainConsumer failed to handle record, offset={}", record.offset(), e);
            }
        }

        if (taskCount > 0) {
            log.info("UpdatedelChainConsumer batch handled, records={}, chainTasks={}", records.size(), taskCount);
        }
    }

    private ChainSyncEvent parseEvent(ConsumerRecord<String, String> record) {
        if (record == null || record.value() == null || record.value().trim().isEmpty()) {
            return null;
        }
        return JSON.parseObject(record.value(), ChainSyncEvent.class);
    }

    private int handleKeys(String actionType, List<Keymanage> keys) throws Exception {
        int total = 0;
        for (List<Keymanage> chunk : chunks(keys, chainBatchSize)) {
            total += handleChunk(actionType, chunk);
        }
        return total;
    }

    private int handleChunk(String actionType, List<Keymanage> keys) throws Exception {
        long startedAt = System.currentTimeMillis();
        CompletionService<ChainResult> completionService = new ExecutorCompletionService<>(chainExecutor);
        int submitted = 0;
        for (Keymanage key : keys) {
            if (key == null || key.getKeyId() == null) {
                continue;
            }
            submitted++;
            completionService.submit(() -> processOne(actionType, key));
        }

        int success = 0;
        int failed = 0;
        List<String> failureSamples = new ArrayList<>();
        for (int i = 0; i < submitted; i++) {
            Future<ChainResult> future = completionService.take();
            ChainResult result = future.get();
            if (result.success) {
                success++;
            } else {
                failed++;
                if (failureSamples.size() < failureSampleSize) {
                    failureSamples.add(result.keyId + ":" + result.message);
                }
            }
        }

        long costMillis = System.currentTimeMillis() - startedAt;
        if (failed > 0) {
            log.warn("Updatedel chain chunk done, actionType={}, total={}, success={}, failed={}, costMs={}, failureSamples={}",
                actionType, submitted, success, failed, costMillis, failureSamples);
        } else if (submitted > 0) {
            log.info("Updatedel chain chunk done, actionType={}, total={}, success={}, failed=0, costMs={}",
                actionType, submitted, success, costMillis);
        }
        return submitted;
    }

    private ChainResult processOne(String actionType, Keymanage key) {
        try {
            boolean success = ChainSyncEvent.TYPE_ROTATE.equals(actionType)
                ? updatedelChainService.processRotateChainSync(key)
                : updatedelChainService.processRevokeChainSync(key);
            return new ChainResult(key.getKeyId(), success, success ? "OK" : "FAILED");
        } catch (Exception e) {
            return new ChainResult(key.getKeyId(), false, e.getClass().getSimpleName());
        }
    }

    private List<List<Keymanage>> chunks(List<Keymanage> source, int batchSize) {
        List<List<Keymanage>> result = new ArrayList<>();
        if (source == null || source.isEmpty()) {
            return result;
        }
        for (int i = 0; i < source.size(); i += batchSize) {
            result.add(source.subList(i, Math.min(i + batchSize, source.size())));
        }
        return result;
    }

    private int effectivePositive(int value, int fallback) {
        return value > 0 ? value : fallback;
    }

    @PreDestroy
    public void shutdown() {
        chainExecutor.shutdown();
        try {
            if (!chainExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                chainExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            chainExecutor.shutdownNow();
        }
    }

    private static class ChainResult {
        private final Long keyId;
        private final boolean success;
        private final String message;

        private ChainResult(Long keyId, boolean success, String message) {
            this.keyId = keyId;
            this.success = success;
            this.message = message;
        }
    }
}
