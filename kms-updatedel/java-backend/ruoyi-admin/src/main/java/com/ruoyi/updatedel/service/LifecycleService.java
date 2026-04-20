package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.service.generator.EccKeyGenerator;
import com.ruoyi.updatedel.service.generator.SsclKeyGenerator;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;
import com.ruoyi.updatedel.domain.KeyAnalysisResultDto;
import java.util.Map;

@Service
public class LifecycleService {
    private static final Logger log = LoggerFactory.getLogger(LifecycleService.class);
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final KeymanageMapper keymanageMapper;
    private final EccKeyGenerator eccKeyGenerator;
    private final SsclKeyGenerator ssclKeyGenerator;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final KeyOperationRecordService keyOperationRecordService;
    private final JdbcTemplate jdbcTemplate;

    @Value("${kms.lifecycle.kafka.chain-task-topic:key_chain_task}")
    private String chainTaskTopic;

    @Value("${kms.lifecycle.auto-update.interval-minutes:30}")
    private long autoUpdateIntervalMinutes;

    @Value("${kms.lifecycle.batch-size:500}")
    private int lifecycleBatchSize;

    @Value("${kms.lifecycle.chain-sync-enabled:true}")
    private boolean chainSyncEnabled;

    @Value("${kms.lifecycle.chain-event-batch-size:500}")
    private int chainEventBatchSize;

    public LifecycleService(
        KeymanageMapper keymanageMapper,
        EccKeyGenerator eccKeyGenerator,
        SsclKeyGenerator ssclKeyGenerator,
        KafkaTemplate<String, String> kafkaTemplate,
        ObjectMapper objectMapper,
        KeyOperationRecordService keyOperationRecordService,
        JdbcTemplate jdbcTemplate
    ) {
        this.keymanageMapper = keymanageMapper;
        this.eccKeyGenerator = eccKeyGenerator;
        this.ssclKeyGenerator = ssclKeyGenerator;
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.keyOperationRecordService = keyOperationRecordService;
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Keymanage> list(Keymanage query) {
        return keymanageMapper.selectkeymanageList(query);
    }

    @Transactional
    public Keymanage createKey(Keymanage key) {
        key.setCreTime(now());
        key.setUpdTime(now());
        if (key.getStatus() == null || key.getStatus().trim().isEmpty()) {
            key.setStatus(KeyStatus.ACTIVE.getCode());
        }
        if (key.getVersion() == null) {
            key.setVersion(1);
        }
        key.setChainStatus("0");
        key.setAutoUpdate(normalizeAutoUpdate(key.getAutoUpdate()));
        key.setKeyValue(generateKeyValue(key));
        keymanageMapper.insertkeymanage(key);
        log.info("createKey 成功: keyId={}, encrytName={}", key.getKeyId(), key.getEncrytName());
        return key;
    }

    public Optional<Keymanage> findById(Long keyId) {
        return Optional.ofNullable(keymanageMapper.selectkeymanageByKeyId(keyId));
    }

    public KeyAnalysisResultDto getAssociationAnalysis(Long keyId) {
        KeyAnalysisResultDto result = new KeyAnalysisResultDto();
        Keymanage key = requireExistingKey(keyId);
        result.setBaseInfo(key);

        String distSql = "SELECT distribute_time, user_name, distribute_type, distribute_status " +
                         "FROM key_distribute_record WHERE key_id = ? ORDER BY distribute_time DESC";
        List<Map<String, Object>> distRecords = jdbcTemplate.queryForList(distSql, keyId);
        result.setDistributeFootprints(distRecords);

        String opSql = "SELECT action_time, action_type, action_source, result_status " +
                       "FROM key_operation_record WHERE key_id = ? ORDER BY action_time DESC";
        List<Map<String, Object>> opRecords = jdbcTemplate.queryForList(opSql, keyId);
        result.setOperationTrails(opRecords);

        return result;
    }

    @Transactional
    public Keymanage rotateKey(Keymanage request) {
        return rotateKey(request, "MANUAL");
    }

    @Transactional
    public Keymanage rotateKey(Keymanage request, String actionSource) {
        Keymanage current = requireExistingKey(request.getKeyId());
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            throw new IllegalStateException("该密钥已被回收，无法更新");
        }

        log.info("rotateKey 开始: keyId={}, encrytType={}, encrytName={}, ua={}",
            current.getKeyId(), current.getEncrytType(), current.getEncrytName(),
            current.getUa() != null ? current.getUa().substring(0, Math.min(8, current.getUa().length())) + "..." : "null");

        Keymanage next = mergeForRotation(current, request);
        next.setVersion(current.getVersion() == null ? 2 : current.getVersion() + 1);
        next.setStatus(KeyStatus.ACTIVE.getCode());
        next.setChainStatus("0");
        next.setUpdTime(now());
        next.setKeyValue(generateKeyValue(next));
        String normalizedActionSource = normalizeActionSource(actionSource);
        applyUpdateProofMetadata(next, request, current, normalizedActionSource);

        keymanageMapper.updatekeymanage(next);
        resetPendingChainState(next.getKeyId());
        keyOperationRecordService.createPendingRecord(next, "UPDATE", normalizedActionSource, "结果已推送，等待用户接收");
        keyOperationRecordService.refreshBatchProof(next.getBatchId(), "UPDATE");
        publishChainEvent(ChainSyncEvent.TYPE_ROTATE, Collections.singletonList(next));
        log.info("rotateKey 完成: keyId={}, newVersion={}", next.getKeyId(), next.getVersion());
        return requireExistingKey(next.getKeyId());
    }

    @Transactional
    public void revokeKey(Long keyId) {
        revokeKey(keyId, "MANUAL");
    }

    @Transactional
    public void revokeKey(Long keyId, String actionSource) {
        Keymanage current = requireExistingKey(keyId);
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            return;
        }
        keymanageMapper.revoke(keyId, KeyStatus.REVOKED.getCode());
        resetPendingChainState(keyId);
        Keymanage revoked = requireExistingKey(keyId);
        keyOperationRecordService.createPendingRecord(revoked, "REVOKE", normalizeActionSource(actionSource), "结果已推送，等待用户接收");
        publishChainEvent(ChainSyncEvent.TYPE_REVOKE, Collections.singletonList(revoked));
    }

    @Transactional
    public int revokeKeys(String userName, List<Long> keyIds) {
        return revokeKeys(userName, keyIds, "MANUAL");
    }

    @Transactional
    public int revokeKeys(String userName, List<Long> keyIds, String actionSource) {
        if (userName == null || userName.trim().isEmpty() || keyIds == null || keyIds.isEmpty()) {
            return 0;
        }

        int affected = 0;
        for (List<Long> chunk : chunks(distinctKeyIds(keyIds), effectiveBatchSize(lifecycleBatchSize))) {
            List<Keymanage> candidates = keymanageMapper.selectRevokeCandidates(userName, chunk, KeyStatus.REVOKED.getCode());
            if (candidates == null || candidates.isEmpty()) {
                continue;
            }

            List<Long> candidateIds = new ArrayList<>(candidates.size());
            String currentTime = now();
            for (Keymanage candidate : candidates) {
                candidateIds.add(candidate.getKeyId());
                candidate.setStatus(KeyStatus.REVOKED.getCode());
                candidate.setChainStatus("0");
                candidate.setChainHash(null);
                candidate.setBlockHeight(null);
                candidate.setUpdTime(currentTime);
            }

            int currentAffected = keymanageMapper.revokeBatch(userName, candidateIds, KeyStatus.REVOKED.getCode());
            if (currentAffected <= 0) {
                continue;
            }
            affected += currentAffected;
            keyOperationRecordService.createPendingRecords(candidates, "REVOKE", normalizeActionSource(actionSource), "结果已推送，等待用户接收");
            publishChainEvent(ChainSyncEvent.TYPE_REVOKE, candidates);
        }
        return affected;
    }

    public void updateAutoUpdate(Long keyId, String autoUpdate) {
        Keymanage current = requireExistingKey(keyId);
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            throw new IllegalStateException("该密钥已被回收，无法修改自动更新状态");
        }
        keymanageMapper.updateAutoUpdate(keyId, normalizeAutoUpdate(autoUpdate));
    }

    public List<Keymanage> listAutoUpdateCandidates() {
        return keymanageMapper.selectAutoUpdateCandidates(nowMinusMinutes(autoUpdateIntervalMinutes()));
    }

    private Keymanage requireExistingKey(Long keyId) {
        return Optional.ofNullable(keymanageMapper.selectkeymanageByKeyId(keyId))
            .orElseThrow(() -> new IllegalStateException("密钥不存在: " + keyId));
    }

    private Keymanage mergeForRotation(Keymanage current, Keymanage request) {
        Keymanage merged = new Keymanage();
        merged.setKeyId(current.getKeyId());
        merged.setUserId(current.getUserId());
        merged.setUserName(valueOrDefault(request.getUserName(), current.getUserName()));
        merged.setUa(valueOrDefault(request.getUa(), current.getUa()));
        merged.setEncrytType(valueOrDefault(request.getEncrytType(), current.getEncrytType()));
        merged.setEncrytName(valueOrDefault(request.getEncrytName(), current.getEncrytName()));
        merged.setKeyName(valueOrDefault(request.getKeyName(), current.getKeyName()));
        merged.setKeyUse(valueOrDefault(request.getKeyUse(), current.getKeyUse()));
        merged.setKeyValue(current.getKeyValue());
        merged.setCreTime(current.getCreTime());
        merged.setAutoUpdate(normalizeAutoUpdate(valueOrDefault(request.getAutoUpdate(), current.getAutoUpdate())));
        merged.setKeyDomain(valueOrDefault(request.getKeyDomain(), current.getKeyDomain()));
        return merged;
    }

    private void applyUpdateProofMetadata(Keymanage next, Keymanage request, Keymanage current, String actionSource) {
        String batchId = valueOrDefault(request.getBatchId(), "single-" + next.getKeyId() + "-" + next.getVersion());
        String rootBatchId = valueOrDefault(request.getRootBatchId(), batchId);
        String parentBatchId = valueOrDefault(request.getParentBatchId(), rootBatchId);
        String treePath = valueOrDefault(request.getTreePath(), rootBatchId + "/0");
        Integer nodeIndex = request.getNodeIndex() == null ? 0 : request.getNodeIndex();
        Integer expectedCount = request.getExpectedCount() == null || request.getExpectedCount() <= 0 ? 1 : request.getExpectedCount();
        Integer treeFanout = request.getTreeFanout() == null || request.getTreeFanout() <= 0 ? 1 : request.getTreeFanout();
        Integer treeLevel = request.getTreeLevel() == null ? 0 : request.getTreeLevel();
        String proofMode = valueOrDefault(request.getProofMode(), "semi_honest");
        String commitmentSeed = valueOrDefault(request.getCommitmentSeed(), batchId);

        next.setBatchId(batchId);
        next.setRootBatchId(rootBatchId);
        next.setParentBatchId(parentBatchId);
        next.setTreePath(treePath);
        next.setTreeLevel(treeLevel);
        next.setNodeIndex(nodeIndex);
        next.setExpectedCount(expectedCount);
        next.setTreeFanout(treeFanout);
        next.setProofMode(proofMode);
        next.setCommitmentSeed(commitmentSeed);
        next.setCommitment(sha256(joinProofParts(
            next.getKeyId(),
            current.getVersion(),
            next.getVersion(),
            batchId,
            parentBatchId,
            treePath,
            actionSource,
            commitmentSeed
        )));
        next.setConsistencyHash(sha256(joinProofParts(parentBatchId, nodeIndex, next.getCommitment())));
        next.setVerifyStatus("0");
        next.setVerifyMessage("waiting for batch proof");
    }

    private String generateKeyValue(Keymanage key) {
        String encrytType = key.getEncrytType() == null ? "" : key.getEncrytType().trim();
        String encrytName = key.getEncrytName() == null ? "" : key.getEncrytName().trim().toUpperCase();

        // AES symmetric encryption
        if ((encrytType.contains("对称") || "AES".equals(encrytName)) && "AES".equals(encrytName)) {
            log.info("generateKeyValue: AES 密钥生成, keyId={}", key.getKeyId());
            return generateAesKey();
        }
        // SM2 certificateless asymmetric encryption
        if ((encrytType.contains("非对称") || "SM2".equals(encrytName)) && "SM2".equals(encrytName)) {
            log.info("generateKeyValue: SM2 密钥生成, keyId={}, ua={}", key.getKeyId(),
                key.getUa() != null ? key.getUa().substring(0, Math.min(8, key.getUa().length())) + "..." : "null");
            if (key.getUa() == null || key.getUa().trim().isEmpty()) {
                throw new IllegalStateException("SM2 密钥更新失败: 用户部分公钥(ua)缺失，keyId=" + key.getKeyId());
            }
            return eccKeyGenerator.generate(key.getUserName(), key.getUa());
        }
        // SSCL certificateless asymmetric encryption
        if ((encrytType.contains("非对称") || "SSCL".equals(encrytName)) && "SSCL".equals(encrytName)) {
            log.info("generateKeyValue: SSCL 密钥生成, keyId={}", key.getKeyId());
            if (key.getUa() == null || key.getUa().trim().isEmpty()) {
                throw new IllegalStateException("SSCL 密钥更新失败: 用户部分公钥(ua)缺失，keyId=" + key.getKeyId());
            }
            return ssclKeyGenerator.generate(key.getUserName(), key.getUa(), key.getKeyDomain());
        }
        // Fallback — unrecognized algorithm, log warning
        log.warn("generateKeyValue: 未匹配到算法类型, keyId={}, encrytType='{}', encrytName='{}', 将返回旧密钥值",
            key.getKeyId(), key.getEncrytType(), key.getEncrytName());
        return key.getKeyValue();
    }

    private String generateAesKey() {
        try {
            KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
            keyGenerator.init(256);
            SecretKey secretKey = keyGenerator.generateKey();
            byte[] bytes = secretKey.getEncoded();
            StringBuilder builder = new StringBuilder();
            for (byte current : bytes) {
                builder.append(String.format("%02x", current));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("AES 密钥生成失败", ex);
        }
    }

    private void publishChainEvent(String actionType, Keymanage keymanage) {
        try {
            kafkaTemplate.send(chainTaskTopic, objectMapper.writeValueAsString(new ChainSyncEvent(actionType, Collections.singletonList(keymanage))));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("上链任务序列化失败", ex);
        }
    }

    private void publishChainEvent(String actionType, List<Keymanage> keys) {
        if (!chainSyncEnabled || keys == null || keys.isEmpty()) {
            return;
        }
        try {
            for (List<Keymanage> chunk : chunks(keys, effectiveBatchSize(chainEventBatchSize))) {
                kafkaTemplate.send(chainTaskTopic, objectMapper.writeValueAsString(new ChainSyncEvent(actionType, chunk)));
            }
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("chain event serialize failed", ex);
        }
    }

    private void resetPendingChainState(Long keyId) {
        keymanageMapper.resetChainState(keyId, "0");
    }

    private String normalizeAutoUpdate(String autoUpdate) {
        if (autoUpdate == null || autoUpdate.trim().isEmpty()) {
            return "0";
        }
        String value = autoUpdate.trim();
        if ("true".equalsIgnoreCase(value) || "enabled".equalsIgnoreCase(value)) {
            return "1";
        }
        if ("false".equalsIgnoreCase(value) || "disabled".equalsIgnoreCase(value)) {
            return "0";
        }
        return value;
    }

    private String valueOrDefault(String candidate, String fallback) {
        return candidate == null || candidate.trim().isEmpty() ? fallback : candidate;
    }

    private String joinProofParts(Object... parts) {
        StringBuilder builder = new StringBuilder();
        for (Object part : parts) {
            if (builder.length() > 0) {
                builder.append('|');
            }
            builder.append(part == null ? "" : part);
        }
        return builder.toString();
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(bytes.length * 2);
            for (byte current : bytes) {
                builder.append(String.format("%02x", current));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 digest unavailable", ex);
        }
    }

    private String normalizeActionSource(String actionSource) {
        return "AUTO".equalsIgnoreCase(actionSource) ? "AUTO" : "MANUAL";
    }

    private String now() {
        return LocalDateTime.now().format(FORMATTER);
    }

    private String nowMinusMinutes(long minutes) {
        return LocalDateTime.now().minusMinutes(minutes).format(FORMATTER);
    }

    private long autoUpdateIntervalMinutes() {
        return autoUpdateIntervalMinutes;
    }

    private List<Long> distinctKeyIds(List<Long> keyIds) {
        Set<Long> distinct = new LinkedHashSet<>();
        for (Long keyId : keyIds) {
            if (keyId != null) {
                distinct.add(keyId);
            }
        }
        return new ArrayList<>(distinct);
    }

    private <T> List<List<T>> chunks(List<T> source, int batchSize) {
        List<List<T>> result = new ArrayList<>();
        if (source == null || source.isEmpty()) {
            return result;
        }
        int size = effectiveBatchSize(batchSize);
        for (int i = 0; i < source.size(); i += size) {
            result.add(source.subList(i, Math.min(i + size, source.size())));
        }
        return result;
    }

    private int effectiveBatchSize(int configuredSize) {
        return configuredSize <= 0 ? 500 : configuredSize;
    }
}
