package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.ChainSyncEvent;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.common.crypto.KeyMaterialEpoch;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.jdbc.core.JdbcTemplate;
import com.ruoyi.updatedel.domain.KeyAnalysisResultDto;
import java.util.Map;

@Service
public class LifecycleService {
    private static final Logger log = LoggerFactory.getLogger(LifecycleService.class);
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final String PENDING_RESULT_MESSAGE = "处理中，请稍后刷新";

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
        // 材料是刚生成的 → 打上当前 ms 版本与算法版本，并标记为可用于解密
        stampMaterialEpoch(key);
        keymanageMapper.insertkeymanage(key);
        log.info("createKey 成功: keyId={}, encrytName={}", key.getKeyId(), key.getEncrytName());
        return key;
    }

    /**
     * 给一条**新签发或刚重新生成材料**的记录打上版本标记。
     *
     * <p>三件事一起做，缺一不可：
     * <ol>
     *   <li>{@code msKeyId} —— 用当前启用版本的 ms 签发，日后按它复算 P_A；</li>
     *   <li>{@code algorithmVersion} —— 当前算法参数版本（SSCL 域参数已改为确定性派生）；</li>
     *   <li>{@code keyMaterialState = active} —— 材料是新的，用户会拿到与之配套的
     *       {@code d_a}，因此可用于解密（与历史那批 {@code legacy_unusable} 区分开）。</li>
     * </ol>
     * 只在字段为空时写入，避免覆盖调用方显式指定的值（例如导入历史记录时）。
     */
    private void stampMaterialEpoch(Keymanage key) {
        if (isBlank(key.getMsKeyId())) {
            key.setMsKeyId(KgcMasterSecret.activeId());
        }
        if (isBlank(key.getAlgorithmVersion())) {
            key.setAlgorithmVersion(KeyMaterialEpoch.ALGORITHM_V1_DERIVED);
        }
        if (isBlank(key.getKeyMaterialState())) {
            key.setKeyMaterialState(KeyMaterialEpoch.STATE_ACTIVE);
        }
    }

    public Optional<Keymanage> findById(Long keyId) {
        return Optional.ofNullable(keymanageMapper.selectkeymanageByKeyId(keyId));
    }

    /**
     * 阶段 4（文档 §5.2）：某逻辑密钥的历史版本（不含当前版本）。
     *
     * <p>当前版本在 {@code keymanage} 表里，历史版本在
     * {@code keymanage_version_history} 表里 —— 这样"读当前状态"仍是单表主键查找，
     * 不会被历史数据拖慢。调用方若要把两者拼成完整版本序列，
     * 需自行把当前版本（version 最大）并进来。
     *
     * <p>⚠️ 返回的是**未脱敏**的对象，调用方必须像 {@code getInfo} 那样
     * 先做属主校验再 {@code KeyValueSanitizer.sanitizeDetail(...)}。
     * 历史版本里同样含 KGC 部分密钥，不校验就成了一条越权读取的旁路。
     */
    public List<Keymanage> findVersionHistory(Long keyId) {
        return keymanageMapper.selectVersionHistory(keyId);
    }

    public KeyAnalysisResultDto getAssociationAnalysis(Long keyId) {
        KeyAnalysisResultDto result = new KeyAnalysisResultDto();
        Keymanage key = requireExistingKey(keyId);
        result.setBaseInfo(key);

        // 分发足迹改读**新链路**的批次表（P5 第 1 步：先迁移消费方，再删旧表）。
        //
        // 旧链路 `kms.key_distribute_record` 是被 P5 删除的对象，但它同时是这个
        // "密钥关联分析"里分发足迹的数据源 —— **先删就会让这里立刻报错**，
        // 这正是计划强调"顺序很重要"的原因。
        //
        // 新表在 `falcon_kds` 库（分发模块所有）。同实例跨库查询在这里是可接受的：
        // 两库一直同实例部署，且 `source_key_id` 本就是逻辑引用 `kms.keymanage.key_id`。
        //
        // 字段名沿用旧的（distribute_time / user_name / distribute_type / distribute_status），
        // 这样 DTO 与前端都不用改 —— 消费方迁移应当对上层透明。
        String distSql = "SELECT b.create_datetime AS distribute_time, " +
                         "COALESCE(u.user_name, CONCAT('用户', b.user_id)) AS user_name, " +
                         "b.wrapping_algorithm AS distribute_type, " +
                         "b.status AS distribute_status " +
                         "FROM falcon_kds.dvadmin_pqkds_distribution_batches b " +
                         "LEFT JOIN sys_user u ON u.user_id = b.user_id " +
                         "WHERE b.source_key_id = ? " +
                         "ORDER BY b.create_datetime DESC";
        List<Map<String, Object>> distRecords = jdbcTemplate.queryForList(distSql, keyId);
        result.setDistributeFootprints(distRecords);

        String opSql = "SELECT action_time, action_type, action_source, result_status " +
                       "FROM key_operation_record WHERE key_id = ? ORDER BY action_time DESC";
        List<Map<String, Object>> opRecords = jdbcTemplate.queryForList(opSql, keyId);
        result.setOperationTrails(opRecords);

        return result;
    }

    /**
     * 判断本次请求是否要求重新生成密钥材料（真正的轮换）。
     * <p>
     * 判据：调用方是否提供了新的用户部分公钥 {@code ua}。
     * <p>
     * 背景：前端「更新」只提交元数据（keyName / keyUse / keyDomain / autoUpdate），
     * 不携带 ua。而此前的控制器逻辑一旦发现 keyName 等字段非空，
     * 就会跳过「仅自动更新」分支、走进完整轮换，导致：
     *   1. 元数据实际上没有被更新；
     *   2. 服务端用自己生成的随机 w 重新计算部分密钥，而客户端持有的是另一个本地私钥分量，
     *      结果返回的新密钥材料客户端无法合成出可用私钥（更新后密钥不可用）；
     *   3. version 每次自增，但用户拿不到对应的新私钥。
     * <p>
     * 因此这里按「是否提供新 ua」显式分流：
     * 提供新 ua → 真轮换；未提供 → 仅更新元数据，version 保持不变。
     */
    public boolean requiresRotation(Keymanage request) {
        if (request == null) {
            return false;
        }
        String ua = request.getUa();
        return ua != null && !ua.trim().isEmpty();
    }

    /**
     * 仅更新密钥元数据，<b>不</b>重新生成密钥材料、<b>不</b>改变 version。
     * <p>
     * 允许更新的字段：key_name / key_use / key_domain / auto_update。
     * 加密相关字段（ua / encrytType / encrytName / keyValue）为保证密钥一致性不予修改，
     * 如需更换密钥材料请走 {@link #rotateKey} 并携带新的 ua。
     *
     * @param request 至少要包含 keyId
     * @return 更新后的密钥
     */
    @Transactional
    public Keymanage updateMetadata(Keymanage request) {
        Keymanage current = requireExistingKey(request.getKeyId());
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            throw new IllegalStateException("该密钥已被回收，无法修改");
        }

        Keymanage patch = new Keymanage();
        patch.setKeyId(current.getKeyId());
        patch.setKeyName(valueOrDefault(request.getKeyName(), current.getKeyName()));
        patch.setKeyUse(valueOrDefault(request.getKeyUse(), current.getKeyUse()));
        patch.setKeyDomain(valueOrDefault(request.getKeyDomain(), current.getKeyDomain()));
        patch.setAutoUpdate(normalizeAutoUpdate(valueOrDefault(request.getAutoUpdate(), current.getAutoUpdate())));
        patch.setUpdTime(now());

        // 加密相关字段保持原值，避免被请求体中的空值或错误值覆盖
        patch.setEncrytType(current.getEncrytType());
        patch.setEncrytName(current.getEncrytName());
        patch.setUserName(current.getUserName());
        patch.setVersion(current.getVersion());

        keymanageMapper.updatekeymanage(patch);
        log.info("updateMetadata 完成: keyId={}, version 保持 {}", current.getKeyId(), current.getVersion());
        return requireExistingKey(current.getKeyId());
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
        // 轮换会**重新生成密钥材料**，所以版本标记必须**强制覆盖**（不能沿用旧值）：
        // 新材料的 P_A 是用当前启用版本的 ms 算的，且用户会拿到配套的新 d_a，
        // 因此它重新变为"可用于解密"。
        next.setMsKeyId(KgcMasterSecret.activeId());
        next.setAlgorithmVersion(KeyMaterialEpoch.ALGORITHM_V1_DERIVED);
        next.setKeyMaterialState(KeyMaterialEpoch.STATE_ACTIVE);
        String normalizedActionSource = normalizeActionSource(actionSource);
        applyUpdateProofMetadata(next, request, current, normalizedActionSource);

        // 阶段 4（文档 §5.2）：**覆盖之前**先把当前版本归档。
        // 位置很关键 —— 必须在 updatekeymanage 之前，否则旧版的 key_value / ua
        // 已被新值覆盖，归档到的是新内容，"历史版本"就名存实亡了。
        // 归档用 INSERT...SELECT 从库里取当前行，不读内存对象（见 Mapper 注释）。
        keymanageMapper.archiveCurrentVersion(
            current.getKeyId(), "ROTATE", normalizedActionSource);

        keymanageMapper.updatekeymanage(next);
        resetPendingChainState(next.getKeyId());
        keyOperationRecordService.createPendingRecord(next, "UPDATE", normalizedActionSource, PENDING_RESULT_MESSAGE);
        refreshBatchProofAfterCommit(next.getBatchId(), "UPDATE");
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
        // 阶段 4（文档 §5.2）：回收前归档当前版本。
        // 回收本身只改 status，但归档仍有价值：链上存证与历史分发记录
        // 需要能回答"这把密钥被回收时是哪一版、材料是什么"。
        String normalizedSource = normalizeActionSource(actionSource);
        keymanageMapper.archiveCurrentVersion(keyId, "REVOKE", normalizedSource);

        keymanageMapper.revoke(keyId, KeyStatus.REVOKED.getCode());
        resetPendingChainState(keyId);
        Keymanage revoked = requireExistingKey(keyId);
        keyOperationRecordService.createPendingRecord(revoked, "REVOKE", normalizedSource, PENDING_RESULT_MESSAGE);
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
            keyOperationRecordService.createPendingRecords(candidates, "REVOKE", normalizeActionSource(actionSource), PENDING_RESULT_MESSAGE);
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

        // AES 分支已按 D12 删除。
        // 它原本会为 encryt_name='AES' 的密钥现生成一把 AES-256 密钥并**明文写进 key_value**。
        // 删除的理由：
        //   1. 架构上「对称密钥完全归分发模块，且统一用 SM4」，主 KMS 不该再养一套对称密钥生成；
        //   2. 界面上根本走不到它 —— 没有任何前端页面能产生 AES 密钥；
        //   3. 运行库里只有 1 行演示数据能触达它（key_id=1，key_value 就是明文 's3cr3tK3y'），
        //      该行已由 22_*.sql 清理。
        // 现在 AES 会落到下面的兜底分支显式失败，而不是静默产生明文对称密钥。

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
        // 未识别算法：此前会静默返回旧密钥值，但调用方已把 version+1 落库，
        // 结果是「版本号变了、密钥材料没变」，数据库与实际密钥不再一致且无任何报错。
        // 现改为显式失败，避免产生不一致数据（例如 PQ 类算法不在此处支持）。
        throw new IllegalStateException(String.format(
            "该算法不支持在生命周期侧重新生成密钥材料，拒绝更新以避免版本与密钥不一致: keyId=%s, encrytType='%s', encrytName='%s'",
            key.getKeyId(), key.getEncrytType(), key.getEncrytName()));
    }

    /**
     * 发布单条上链任务。
     * <p>
     * 注意：本方法此前<strong>未</strong>检查 chainSyncEnabled，而列表重载检查了，
     * 导致关闭上链同步时单条更新/回收仍会投递任务，行为不一致。
     * 现与列表重载保持同一判据。
     */
    private void publishChainEvent(String actionType, Keymanage keymanage) {
        if (!chainSyncEnabled || keymanage == null) {
            return;
        }
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

    private void refreshBatchProofAfterCommit(final String batchId, final String actionType) {
        if (batchId == null || batchId.trim().isEmpty()) {
            return;
        }
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            keyOperationRecordService.refreshBatchProofWithRetry(batchId, actionType);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                keyOperationRecordService.refreshBatchProofWithRetry(batchId, actionType);
            }
        });
    }

    /**
     * 本次请求是否**真的**改变了自动更新开关。
     *
     * 为什么需要这个判断（2026-09-24 用户反馈的逻辑错误）：
     * 权限拦截原先写成"只要请求里带了非空的 autoUpdate 就要自动更新权限"。
     * 而两个前端的"更新密钥"弹窗都会把开关的当前值一起提交
     * （`autoUpdate: '1'/'0'`，恒非空），于是**只想改密钥名称的用户**
     * 会被拦下，报错还是"当前用户没有自动更新操作权限" —— 与他在做的事完全对不上。
     *
     * 现在只有在**值确实发生变化**时才要求权限：
     * 既修掉了误拦，也保留了原本的防绕过意图 ——
     * 想借"顺手改个元数据"把自动更新打开，依然会被拦住。
     *
     * 比较用 normalizeAutoUpdate 归一化后再比，避免 'true'/'enabled'/'1' 这类
     * 等价写法被误判成"变了"。
     */
    public boolean changesAutoUpdate(Keymanage current, String requested) {
        if (requested == null || requested.trim().isEmpty()) {
            return false;
        }
        String currentValue = current == null ? null : current.getAutoUpdate();
        return !normalizeAutoUpdate(requested).equals(normalizeAutoUpdate(currentValue));
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

    /** 空串判定（含全空白）。与 generate 域的同名helper保持一致语义。 */
    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
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
