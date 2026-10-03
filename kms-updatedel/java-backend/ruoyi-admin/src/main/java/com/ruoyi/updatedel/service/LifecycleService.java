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

    // 算法名常量。文档 §5.3 按算法给出**不同**的更新策略，因此判断必须按算法分流，
    // 而散落的字符串字面量正是"改了这里漏了那里"的来源。
    private static final String SM2 = "SM2";
    private static final String SSCL = "SSCL";
    private static final String KYBER = "KYBER";
    private static final String FALCON = "FALCON";

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

        // 阶段 7（文档 §8.6）：补上**创建**事件的存证。
        //
        // 此前链上只有 ROTATE / REVOKE 两种事件，创建根本没有 ——
        // 于是"这把密钥什么时候产生的、当时是哪份公开材料"在链上查不到，
        // 而那恰恰是审计最基本的追问：没有起点，后续的更新与回收
        // 都缺一个可对照的基准。
        //
        // 与轮换/回收一样走事务提交后再投递（见 publishChainEvent），
        // 避免事务未提交就发事件导致链上记录指向不存在的数据。
        publishChainEvent(ChainSyncEvent.TYPE_KEY_CREATED, key);
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

        // 阶段 7（文档 §8.3）：泄漏影响面还要回答"哪些预分配池项依赖它、
        // 哪些节点受影响"—— 原先只给了分发足迹与操作轨迹，不足以做处置决策。
        //
        // 关联路径：密钥属于某个用户 → 该用户即某个节点（阶段 2 的一一映射）
        //           → 该节点的预分配池项即"依赖它的资源"。
        // 这与 §7.6「长期密钥回收后连带失效相关池项」用的是**同一条链**，
        // 因此这里的结论可以直接指导处置：失效哪些池项、通知哪些节点。
        //
        // 仍只统计 READY/RESERVED —— 已消费的是历史事实，改了会让审计对不上。
        String poolSql =
            "SELECT p.pool_id, COUNT(*) AS item_count, p.status " +
            "FROM falcon_kds.dvadmin_pqkds_pre_distributed_keys p " +
            "JOIN falcon_kds.dvadmin_pqkds_nodes n " +
            "  ON (n.id = p.node1_id OR n.id = p.node2_id) " +
            "WHERE n.sys_user_id = ? AND p.status IN ('READY','unused','RESERVED') " +
            "GROUP BY p.pool_id, p.status ORDER BY p.pool_id";
        try {
            result.setAffectedPoolItems(jdbcTemplate.queryForList(poolSql, key.getUserId()));
        } catch (RuntimeException ex) {
            // 池项统计失败不该让整个分析失败 —— 分发足迹与操作轨迹仍有价值
            log.warn("泄漏关联分析：池项查询失败 keyId={} err={}", keyId, ex.getMessage());
            result.setAffectedPoolItems(java.util.Collections.emptyList());
        }

        // 受影响节点：把分发批次里的 node_ids（JSON 数组）展开成节点。
        // 用 JSON_TABLE 在库侧展开，避免把整串拉到 Java 里再解析 ——
        // 批次多时那个字符串可能很长。
        String nodeSql =
            "SELECT DISTINCT n.node_id, n.name, n.permission_level, n.domain_id " +
            "FROM falcon_kds.dvadmin_pqkds_distribution_batches b " +
            "JOIN JSON_TABLE(b.node_ids, '$[*]' COLUMNS (nid INT PATH '$')) AS t " +
            "JOIN falcon_kds.dvadmin_pqkds_nodes n ON n.id = t.nid " +
            "WHERE b.source_key_id = ?";
        try {
            result.setAffectedNodes(jdbcTemplate.queryForList(nodeSql, keyId));
        } catch (RuntimeException ex) {
            log.warn("泄漏关联分析：受影响节点查询失败 keyId={} err={}", keyId, ex.getMessage());
            result.setAffectedNodes(java.util.Collections.emptyList());
        }

        return result;
    }

    /**
     * KMS-014（计划 §7 阶段 6「泄漏分析按具体密钥版本追踪受影响信封、池项和会话」）
     * ：以**节点长期密钥**（`NodeLongTermKey` 的 keyId + 版本）为线索的泄漏分析。
     *
     * <p>为什么需要第二条入口，而不是把 keyId 塞进现有那个
     * -------------------------------------------------------
     * 主 KMS 的 `keymanage.key_id`（bigint）与分发模块 `NodeLongTermKey.key_id`
     * （字符串，如 `KRB-XXXX-KYBER-1a2b3c4d`）是**两个不同的标识空间**：
     * 前者是用户密钥，后者是节点长期密钥。KMS-008 之后的节点到节点分发
     * **完全不用用户密钥**（`source_key_id` 为 NULL 是如实记录），
     * 所以"某把用户密钥的泄漏分析里没有新批次"是对的 —— 新批次跟它无关。
     * 真正的处置问题变成了："**某台节点的某版长期密钥**泄漏了，
     * 哪些信封/池项/会话受影响、该失效什么。"
     *
     * <p>这正是 KMS-008 如实记录的过渡缺口所指的关联键
     * （`PreDistributedKey.long_term_key_id/version`、`SessionKey.recipient_key_id/
     * recipient_key_version` 与 `falcon_key_id/falcon_key_version`）。
     *
     * <p>查询与 `getAssociationAnalysis` 同一条纪律：跨库只读、失败不让整体失败
     * （每一段各自 catch 后置空并记 warning —— "分析少一段"仍比"分析整体 500"有用）。
     *
     * @param longTermKeyId 节点长期密钥的业务 keyId（字符串，逐字比对）
     * @param version       版本；0 或缺省表示**该 keyId 的全部版本**（keyId 本身
     *                      在 KMS-006 的模型里标识一把密钥，版本才是一次换代）
     */
    public KeyAnalysisResultDto getNodeKeyLeakAnalysis(String longTermKeyId, Integer version) {
        KeyAnalysisResultDto result = new KeyAnalysisResultDto();
        String kid = longTermKeyId == null ? "" : longTermKeyId.trim();
        if (kid.isEmpty()) {
            return result;
        }
        Integer ver = (version == null || version <= 0) ? null : version;
        String verClause = ver == null ? "" : " AND long_term_key_version = ? ";

        // ---- 信封（新模型里信封就是池项行；按 KMS-010 的口径逐字比对）----
        String envelopeSql =
            "SELECT p.pool_id, p.key_index, p.status, p.long_term_key_id, p.long_term_key_version, " +
            "       p.expires_at " +
            "FROM falcon_kds.dvadmin_pqkds_pre_distributed_keys p " +
            "WHERE p.recipient_type = 'node' AND p.long_term_key_id = ? " + verClause +
            "ORDER BY p.create_datetime DESC LIMIT 200";
        try {
            result.setDistributeFootprints(ver == null
                ? jdbcTemplate.queryForList(envelopeSql, kid)
                : jdbcTemplate.queryForList(envelopeSql, kid, ver));
        } catch (RuntimeException ex) {
            log.warn("节点密钥泄漏分析：信封查询失败 keyId={} v={} err={}", kid, ver, ex.getMessage());
            result.setDistributeFootprints(Collections.emptyList());
        }

        // ---- 池项：仍可取用的（READY 含旧拼写；已消费的是历史事实）----
        String poolSql =
            "SELECT p.pool_id, COUNT(*) AS item_count, p.status " +
            "FROM falcon_kds.dvadmin_pqkds_pre_distributed_keys p " +
            "WHERE p.long_term_key_id = ? " + verClause +
            "  AND p.status IN ('READY','unused','RESERVED') " +
            "GROUP BY p.pool_id, p.status ORDER BY p.pool_id";
        try {
            result.setAffectedPoolItems(ver == null
                ? jdbcTemplate.queryForList(poolSql, kid)
                : jdbcTemplate.queryForList(poolSql, kid, ver));
        } catch (RuntimeException ex) {
            log.warn("节点密钥泄漏分析：池项查询失败 keyId={} v={} err={}", kid, ver, ex.getMessage());
            result.setAffectedPoolItems(Collections.emptyList());
        }

        // ---- 会话：两处引用都要查（接收方保护密钥 / 发送方签名密钥）----
        String sessionSql =
            "SELECT s.session_id, s.status, s.session_type, " +
            "       s.recipient_key_id, s.recipient_key_version, " +
            "       s.falcon_key_id, s.falcon_key_version, " +
            "       n1.node_id AS sender_node_id, n2.node_id AS receiver_node_id " +
            "FROM falcon_kds.dvadmin_pqkds_session_keys s " +
            "JOIN falcon_kds.dvadmin_pqkds_nodes n1 ON n1.id = s.node1_id " +
            "JOIN falcon_kds.dvadmin_pqkds_nodes n2 ON n2.id = s.node2_id " +
            "WHERE (s.recipient_key_id = ?" + (ver == null ? "" : " AND s.recipient_key_version = ?") + ") " +
            "   OR (s.falcon_key_id = ?" + (ver == null ? "" : " AND s.falcon_key_version = ?") + ") " +
            "ORDER BY s.create_datetime DESC LIMIT 200";
        try {
            List<Object> args = new ArrayList<>();
            args.add(kid);
            if (ver != null) {
                args.add(ver);
            }
            args.add(kid);
            if (ver != null) {
                args.add(ver);
            }
            result.setOperationTrails(jdbcTemplate.queryForList(sessionSql, args.toArray()));
        } catch (RuntimeException ex) {
            log.warn("节点密钥泄漏分析：会话查询失败 keyId={} v={} err={}", kid, ver, ex.getMessage());
            result.setOperationTrails(Collections.emptyList());
        }

        // ---- 受影响节点：引用过这一版的所有节点（去重）----
        String nodeSql =
            "SELECT DISTINCT n.node_id, n.name, n.permission_level, n.domain_id " +
            "FROM falcon_kds.dvadmin_pqkds_nodes n " +
            "WHERE n.id IN (" +
            "  SELECT p.node1_id FROM falcon_kds.dvadmin_pqkds_pre_distributed_keys p " +
            "    WHERE p.long_term_key_id = ?" + (ver == null ? "" : " AND p.long_term_key_version = ?") +
            "    AND p.node1_id IS NOT NULL " +
            "  UNION " +
            "  SELECT p.node2_id FROM falcon_kds.dvadmin_pqkds_pre_distributed_keys p " +
            "    WHERE p.long_term_key_id = ?" + (ver == null ? "" : " AND p.long_term_key_version = ?") +
            "    AND p.node2_id IS NOT NULL)";
        try {
            Object[] args = ver == null ? new Object[]{kid, kid} : new Object[]{kid, ver, kid, ver};
            result.setAffectedNodes(jdbcTemplate.queryForList(nodeSql, args));
        } catch (RuntimeException ex) {
            log.warn("节点密钥泄漏分析：受影响节点查询失败 keyId={} v={} err={}", kid, ver, ex.getMessage());
            result.setAffectedNodes(Collections.emptyList());
        }

        return result;
    }

    /**
     * 判断本次请求是否要求重新生成密钥材料（真正的轮换）。
     * <p>
     * 判据：调用方是否**显式**声明 {@code rotate}。
     * <p>
     * 背景：前端「更新」只提交元数据（keyName / keyUse / keyDomain / autoUpdate），
     * 不携带 ua。而此前的控制器逻辑一旦发现 keyName 等字段非空，
     * 就会跳过「仅自动更新」分支、走进完整轮换，导致：
     *   1. 元数据实际上没有被更新；
     *   2. 服务端用自己生成的随机 w 重新计算部分密钥，而客户端持有的是另一个本地私钥分量，
     *      结果返回的新密钥材料客户端无法合成出可用私钥（更新后密钥不可用）；
     *   3. version 每次自增，但用户拿不到对应的新私钥。
     * <p>
     * <b>为什么判据从"有没有 ua"改成显式标志（阶段 4 / 文档 §5.3）</b>
     * <p>
     * 文档 §5.3 要求 SM2 / SSCL 更新时<b>保留</b>节点侧秘密 {@code u} 与公开量
     * {@code uA}，只让 KGC 重新生成随机 {@code w} 和部分密钥。也就是说，
     * 一次**正确的**部分刷新请求所携带的 uA，与库中已有的那个是<b>同一个值</b>。
     * <p>
     * 于是"有没有 ua"这个信号同时在两个方向上出错：
     * <ul>
     *   <li>部分刷新带着（相同的）uA 来 → 看起来像"提供了新 ua" → 被判成轮换，
     *       虽然结果碰巧正确，但判断依据是错的；</li>
     *   <li>只改元数据、但顺手把库里的 uA 回填进请求体 → 也被判成轮换，
     *       而调用方的本意恰恰是不动密钥材料。</li>
     * </ul>
     * 两种误判方向相反，根因相同：把"数据恰好在那"当成了"意图在那"。
     * 现在由调用方声明意图，ua 退回到它应有的角色 —— 只作为
     * {@link #rotateKey} 里的一致性校验输入。
     *
     * @param request 至少要知道它有没有声明 rotate
     * @return true 表示走 {@link #rotateKey}；false 表示走 {@link #updateMetadata}
     */
    public boolean requiresRotation(Keymanage request) {
        if (request == null) {
            return false;
        }
        // 兼容期：显式标志优先；未提供标志时**不退化为旧的 ua 判据**。
        //
        // 退回去看着"向后兼容"，实际会把上面那条误判路径原样保留下来，
        // 而它正是这次要消掉的东西。旧前端不带标志的后果是「更新」按钮
        // 只会改元数据 —— 那是个安全的失败方向（不产生错误的版本号、
        // 不写链、不会让客户端持有解不开的私钥），且界面上能立刻看出来。
        return Boolean.TRUE.equals(request.getRotate());
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

        String algorithm = normalizeAlgorithmName(current.getEncrytName());
        Keymanage next = mergeForRotation(current, request);

        // ------------------------------------------------------------------
        // 阶段 4 / 文档 §5.3：各算法的更新策略**不同**，这里按算法显式分流。
        //
        // 为什么必须分开：文档 §5.1 把"更新"定义为「保留 key_id、产生新 version」，
        // 而 §5.3 给的三种做法差别很大。此前不分算法、全部丢给 `generateKeyValue()`
        // 重新算一遍，掩盖了两件事：
        //   * 客户端**必须**重新提交一份 uA —— 于是界面上"更新"得先点
        //     「重新生成本地密钥材料」，而那个按钮造的是**新的 u 和新的 uA**，
        //     并不是文档要求的"保留 u、只换 KGC 那一半"。文档说 §5.3 未实现，
        //     指的正是这里：能跑通，但跑的不是 §5.3 描述的那个协议；
        //   * 真正做不到的算法（Kyber / Falcon，私钥根本不在服务端）与
        //     "做得到但做法不对"混在同一条路径里，都只在生成函数里抛一句笼统的话。
        // ------------------------------------------------------------------

        // --- Kyber / Falcon：文档 §5.3 要求由**节点侧**重新 KeyGen -------------
        // 服务端没有这两者的私钥，造不出新版本。这里显式失败并指出正确路径，
        // 而不是让它落到下面的兜底分支报一句与算法无关的话。
        if (KYBER.equals(algorithm) || FALCON.equals(algorithm)) {
            throw new IllegalStateException(String.format(
                "%s 的更新必须由节点侧重新生成密钥对（文档 §5.3）：私钥不在服务端，"
                    + "服务端无法为它产生新版本。请由节点本地重新 KeyGen 后上传新公钥，"
                    + "或改用「密钥生成」新建一把。keyId=%s",
                algorithm, current.getKeyId()));
        }

        // --- SM2 / SSCL：无证书部分刷新（文档 §5.3）---------------------------
        if (SM2.equals(algorithm) || SSCL.equals(algorithm)) {
            String currentUa = current.getUa() == null ? "" : current.getUa().trim();
            if (currentUa.isEmpty()) {
                throw new IllegalStateException(String.format(
                    "无法更新：该密钥没有记录用户部分公钥 uA，缺了它就算不出公钥点 P_A。keyId=%s",
                    current.getKeyId()));
            }
            String submittedUa = request.getUa() == null ? "" : request.getUa().trim();
            if (!submittedUa.isEmpty() && !submittedUa.equalsIgnoreCase(currentUa)) {
                // 换 uA 就是换节点侧秘密，等于换了一把密钥 —— 不是"更新"。
                // 放行的后果很具体：库里出现一条"version +1"的记录，而持有该
                // key_id 私钥文件的人在新版本上已经解不开任何东西，
                // 审计从版本号上也看不出发生过这种事。
                throw new IllegalStateException(String.format(
                    "更新必须保留用户部分公钥 uA（文档 §5.3）：节点侧秘密份额不变，只刷新 KGC 部分。"
                        + "换 uA 等于换密钥，请改用「密钥生成」新建一把。keyId=%s",
                    current.getKeyId()));
            }
            // 显式保留 uA，不依赖 mergeForRotation 的默认值 —— 那个默认值是对的，
            // 但"对"应当是显式的：日后若有人改了默认值，这里会静默换掉 uA，
            // 而 §5.3 的整条协议正是建立在"uA 不变"之上。
            next.setUa(currentUa);

            log.info("rotateKey 开始（{} 部分刷新）: keyId={}, ua={} 保留不变，"
                    + "将由 KGC 重新生成随机 w 与部分密钥，节点侧 u 与完整私钥 d_A 需在客户端重算",
                algorithm, current.getKeyId(),
                currentUa.substring(0, Math.min(8, currentUa.length())) + "...");
        }
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
        publishChainEvent(ChainSyncEvent.TYPE_KEY_UPDATED, Collections.singletonList(next));
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
        publishChainEvent(ChainSyncEvent.TYPE_KEY_REVOKED, Collections.singletonList(revoked));
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
            publishChainEvent(ChainSyncEvent.TYPE_KEY_REVOKED, candidates);
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

    /**
     * 把 `encryt_name` 归一到用于分流的算法名。
     *
     * <p>库里这一列的历史取值并不统一（`sm2` / `SM2` / `SM2 国密` 都出现过），
     * 所以按算法分流之前必须先归一 —— 否则同一算法会走到不同分支，
     * 而"更新时某个算法没走它该走的协议"这种偏差从版本号上完全看不出来。
     *
     * <p>按**从长到短的已知算法名**做包含匹配；认不出来时返回原文大写，
     * 让调用方的兜底分支去显式报错，而不是在这里猜一个算法出来 ——
     * 猜错的代价是拿一个不相干的生成器去算密钥材料。
     */
    private String normalizeAlgorithmName(String encrytName) {
        if (encrytName == null) {
            return "";
        }
        String upper = encrytName.trim().toUpperCase();
        for (String known : new String[] {SSCL, KYBER, FALCON, SM2}) {
            if (upper.contains(known)) {
                return known;
            }
        }
        return upper;
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
