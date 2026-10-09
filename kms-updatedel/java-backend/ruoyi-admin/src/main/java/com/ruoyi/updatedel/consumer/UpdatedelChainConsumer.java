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

    @Value("${KMS_CHAIN_WRITES_ENABLED:false}")
    private boolean chainWritesEnabled;

    @Value("${KMS_CHAIN_CONSUMER_ENABLED:false}")
    private boolean chainConsumerEnabled;

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
        autoStartup = "#{${KMS_CHAIN_WRITES_ENABLED:false} && ${KMS_CHAIN_CONSUMER_ENABLED:false} && ${kms.lifecycle.chain-sync-enabled:true}}",
        properties = {
            "max.poll.records=${kms.lifecycle.chain-max-poll-records:10}",
            "max.poll.interval.ms=${kms.lifecycle.chain-max-poll-interval-ms:900000}"
        }
    )
    public void onMessage(List<ConsumerRecord<String, String>> records) {
        if (!chainWritesEnabled || !chainConsumerEnabled || !updatedelChainService.isChainWriteEnabled()) {
            log.info("CHAIN_WRITES_PAUSED: lifecycle chain consumer disabled");
            return;
        }
        int taskCount = 0;
        for (ConsumerRecord<String, String> record : records) {
            try {
                ChainSyncEvent event = parseEvent(record);
                if (event == null || event.getKeys() == null || event.getKeys().isEmpty()) {
                    continue;
                }

                // ⚠️ 必须经 `normalize` 归一，**不能**直接拿新常量去比。
                //
                // 阶段 7（§8.6）把事件类型改名为 KEY_CREATED / KEY_UPDATED /
                // KEY_REVOKED / KEY_DISTRIBUTED，并保留了 ROTATE / REVOKE 两个
                // 历史值用于兼容**已投递过的事件**。但当时的改动只动了发布侧，
                // 消费侧这一行还在拿 @Deprecated 的 TYPE_ROTATE / TYPE_REVOKE 比 ——
                // 而发布侧从此只发新值，于是**更新与回收在链上完全停止落账**：
                // 接口返回成功、库里 status/version 都对，只有链上查不到。
                // 现象与"链本身出问题"一模一样，很容易朝错误的方向排查。
                //
                // 用 normalize 之后，新旧值都收敛到同一语义，两边再也不会漂移。
                String actionType = ChainSyncEvent.normalize(event.getActionType());
                if (ChainSyncEvent.TYPE_KEY_UPDATED.equals(actionType)
                    || ChainSyncEvent.TYPE_KEY_REVOKED.equals(actionType)
                    || ChainSyncEvent.TYPE_KEY_CREATED.equals(actionType)) {
                    taskCount += handleKeys(actionType, event.getKeys());
                } else if (ChainSyncEvent.SESSION_TRAIL_ONLY_TYPES.contains(actionType)
                    || ChainSyncEvent.AUTH_TRAIL_ONLY_TYPES.contains(actionType)) {
                    // KMS-014 / 节点多级授权：这些事件**显式**只留痕、不改状态 ——
                    // 会话状态由 PQKDS 侧的状态机负责、授权状态由 pqkds 的授权表负责
                    // （链上消费者若也去改，系统里就有两套"现在是什么状态"的答案）。
                    // 写成显式分支而不是靠 else 兜底：兜底分支的语义是
                    // "不认识"，而这些是**认识的**，只是不该动状态 ——
                    // 混在一起之后，"新增事件忘了处理"与"刻意不处理"就无法区分。
                    //
                    // ⚠️ 授权类事件的 keyId 装的是**申请单主键**、不是密钥主键
                    //    （见 `ChainSyncEvent.AUTH_TRAIL_ONLY_TYPES` 的说明），
                    //    所以这里只记日志、绝不按 keyId 去查密钥。
                    log.info("UpdatedelChainConsumer trail-only event, actionType={} keys={}",
                        actionType, event.getKeys().size());
                } else {
                    // KEY_DISTRIBUTED 由分发模块产生，尚未接通投递（见 §8.6 的说明），
                    // 这里如实记 info 而不是 debug：否则"事件投递了却什么都没发生"
                    // 在默认日志级别下完全不可见。
                    log.info("UpdatedelChainConsumer ignored actionType={}", actionType);
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
            // actionType 已由调用点 normalize 过，这里比较的是规范值。
            boolean success;
            if (ChainSyncEvent.TYPE_KEY_CREATED.equals(actionType)) {
                success = updatedelChainService.processCreateChainSync(key);
            } else if (ChainSyncEvent.TYPE_KEY_UPDATED.equals(actionType)) {
                success = updatedelChainService.processRotateChainSync(key);
            } else {
                success = updatedelChainService.processRevokeChainSync(key);
            }
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
