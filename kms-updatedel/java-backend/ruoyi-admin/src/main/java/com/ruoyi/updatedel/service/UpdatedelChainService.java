package com.ruoyi.updatedel.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.updatedel.contracts.KeyEvidence;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import java.io.File;
import java.math.BigInteger;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.PostConstruct;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.encoders.Hex;
import org.fisco.bcos.sdk.BcosSDK;
import org.fisco.bcos.sdk.client.Client;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;
import org.fisco.bcos.sdk.model.TransactionReceipt;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class UpdatedelChainService {

    private static final Logger log = LoggerFactory.getLogger(UpdatedelChainService.class);
    private static final BigInteger SM2_GX = new BigInteger("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7", 16);
    private static final BigInteger SM2_GY = new BigInteger("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0", 16);
    private static final int REVOKED_STATUS = 3;
    private static final int ACTIVE_STATUS = 0;

    private final KeymanageMapper keymanageMapper;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final KeyOperationRecordService keyOperationRecordService;

    @Value("${fisco.contract-address:0x0000000000000000000000000000000000000000}")
    private String contractAddress;

    @Value("${fisco.host:fisco-node}")
    private String fiscoHost;

    @Value("${fisco.private-key:}")
    private String fiscoPrivateKey;

    @Value("${kms.lifecycle.kafka.chain-result-topic:key_chain_result}")
    private String chainResultTopic;

    @Value("${kms.lifecycle.chain-detail-log-enabled:false}")
    private boolean chainDetailLogEnabled;

    @Value("${KMS_CHAIN_BACKEND:legacy}")
    private String chainBackend = "legacy";

    @Value("${FABRIC_DID_CHAIN_ID:}")
    private String fabricChainId = "";

    private FiscoBcosWrapper fiscoWrapper;

    public boolean isFabricDidBackend() {
        String selected = chainBackend == null ? "legacy" : chainBackend.trim().toLowerCase(java.util.Locale.ROOT);
        if (!"legacy".equals(selected) && !"fabric-did".equals(selected)) {
            throw new IllegalStateException("KMS_CHAIN_BACKEND 必须为 legacy 或 fabric-did");
        }
        return "fabric-did".equals(selected);
    }

    public String getChainProvider() {
        return isFabricDidBackend() ? "FABRIC_DID" : "LEGACY_FISCO";
    }

    public String getChainId() {
        return isFabricDidBackend() ? fabricChainId : "fisco:group-1:" + contractAddress;
    }

    private boolean unsupportedLegacySync(Keymanage key, String action) {
        if (!isFabricDidBackend()) {
            return false;
        }
        // 旧 Keymanage 不是节点长期密钥登记行，不能用数字主键/摘要伪造 DID 绑定。
        // 真正的四算法公钥由 PQKDS 登记事务的 outbox 处理；这里不回退旧链。
        markFailed(key.getKeyId());
        publishChainResult(key.getKeyId(), action, "2", null, null, "UNSUPPORTED_LEGACY_KEY_MODEL_FOR_DID");
        log.warn("Fabric DID 不执行旧密钥合约动作: keyId={} action={}", key.getKeyId(), action);
        return true;
    }

    public UpdatedelChainService(KeymanageMapper keymanageMapper, KafkaTemplate<String, String> kafkaTemplate,
                                 KeyOperationRecordService keyOperationRecordService) {
        this.keymanageMapper = keymanageMapper;
        this.kafkaTemplate = kafkaTemplate;
        this.keyOperationRecordService = keyOperationRecordService;
    }

    @PostConstruct
    public void init() {
        isFabricDidBackend(); // 配置拼错必须启动失败，不能默认偷写旧链。
        this.fiscoWrapper = null;
        log.info("Lifecycle FISCO wrapper will initialize lazily when chain sync is triggered");
    }

    /**
     * 把一条**新创建**的密钥登记到链上（文档 §8.6 的 KEY_CREATED）。
     *
     * <h2>为什么这个方法是必需的，而不是"多存一笔"</h2>
     * 契约 {@code KeyEvidence} 的两个写方法都以记录必须存在为前置条件：
     * <pre>
     *   rotateKey        require(k.keyId != 0, "key missing")
     *   changeKeyStatus  require(records[_keyId].keyId != 0, "key missing")
     * </pre>
     * 而记录只能由 {@code uploadKey} 建立。本服务此前**从未调用过 uploadKey**，
     * 所以更新与回收在链上全部 revert —— 但 revert 的回执仍然是"交易成功"，
     * 事件自然是空的，于是失败被记为 {@code MISSING_ROTATE_EVENT} /
     * {@code MISSING_STATUS_EVENT}。那两个名字把原因指向"事件解析"，
     * 而真实原因是"合约里没有这条记录"，排查方向完全被带偏。
     *
     * <p>所以补上 uploadKey 不只是为了"多一个 KEY_CREATED 事件"——
     * 它是另外两条链路能真正落链的**前提**。
     *
     * <h2>上链的公开材料</h2>
     * SM2 / SSCL 上链的是可解密的加密目标点 {@code P_A}（与 rotate 用的是同一个
     * {@link #calculatePA}）。<b>不</b>上链节点侧秘密 {@code u}、完整私钥 {@code d_A}、
     * 或任何 SM4 明文 —— 契约里这一列叫 publicKey，字面意思就是公开量。
     */
    public boolean processCreateChainSync(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyId() == null) {
            return false;
        }
        if (unsupportedLegacySync(keymanage, "CREATE_KEY")) {
            return false;
        }

        try {
            String publicMaterial = calculatePA(keymanage);
            if (publicMaterial == null) {
                // 算不出公开材料就不上链：宁可让链上没有这条记录（状态停在"待上链"），
                // 也不要把一个空串写进去 —— 那会占住 keyId，导致**之后**的 rotateKey
                // 因为 "key exists" 永远失败，而且失败原因看上去与这里毫无关系。
                markFailed(keymanage.getKeyId());
                publishChainResult(keymanage.getKeyId(), "CREATE_KEY", "2", null, null, "PA_CALC_FAILED");
                return false;
            }

            if (!ensureFiscoWrapper()) {
                markFailed(keymanage.getKeyId());
                publishChainResult(keymanage.getKeyId(), "CREATE_KEY", "2", null, null, "FISCO_NOT_READY");
                return false;
            }

            TransactionReceipt receipt = fiscoWrapper.uploadKey(
                keymanage.getKeyId(),
                keymanage.getUserName(),
                publicMaterial,
                keymanage.getEncrytName(),
                keymanage.getKeyUse(),
                "1".equals(keymanage.getAutoUpdate()),
                keymanage.getVersion() == null ? 1 : keymanage.getVersion());
            return handleCreateReceipt(keymanage.getKeyId(), receipt);
        } catch (Exception e) {
            logDetailFailure("Create chain sync failed", keymanage.getKeyId(), e);
            markFailed(keymanage.getKeyId());
            publishChainResult(keymanage.getKeyId(), "CREATE_KEY", "2", null, null, e.getClass().getSimpleName());
            return false;
        }
    }

    /**
     * 把一条**通用生命周期事件**记到链上（文档 §8.6）。
     *
     * <p>与 {@link #processCreateChainSync} 等方法的关键差别：这里**不要求**
     * keyId 在本链上已登记，也不改动任何 KeyRecord 状态。分发模块要记的
     * KEY_DISTRIBUTED 正属于这一类 —— 被分发的密钥是链上已有记录的一次**使用**，
     * 不是它的状态变迁；而按 keyId 去 rotateKey 既语义不符，也会因为
     * "记录不存在"而失败。
     *
     * <p>同时这里**不写** key_operation_record、不更新 keymanage.chain_status：
     * 那不是本服务的密钥，改它的状态会污染生命周期侧的审计。
     * 事件本身留在链上，这才是分发侧要的存证。
     *
     * @return 交易哈希；链服务未就绪或交易失败时返回 {@code null}（调用方据此报错）
     */
    public String recordLifecycleEvent(String eventType, long keyId, int version,
                                       String nodeId, String publicMaterialHash) {
        if (!ensureFiscoWrapper()) {
            log.warn("记录链上事件失败：FISCO 未就绪, type={} keyId={}", eventType, keyId);
            return null;
        }
        try {
            TransactionReceipt receipt = fiscoWrapper.recordEvent(
                eventType,
                BigInteger.valueOf(keyId),
                BigInteger.valueOf(version),
                nodeId == null ? "" : nodeId,
                publicMaterialHash == null ? "" : publicMaterialHash);
            if (receipt == null || !receipt.isStatusOK()) {
                log.warn("记录链上事件交易失败, type={} keyId={} status={}",
                    eventType, keyId, receipt == null ? "null" : receipt.getStatus());
                return null;
            }
            // 校验事件确实落在回执里再回报成功。
            // 只看"交易成功"是不够的 —— 本次排查里 MISSING_*_EVENT 正是
            // "交易成功但事件为空"，两者混淆了一次。这里在源头就分开。
            List<KeyEvidence.KeyLifecycleEventEventResponse> events =
                fiscoWrapper.getKeyLifecycleEvents(receipt);
            if (events.isEmpty()) {
                log.warn("记录链上事件交易成功但回执无事件（事件签名可能不匹配）, type={} keyId={}",
                    eventType, keyId);
                return null;
            }
            return receipt.getTransactionHash();
        } catch (Exception e) {
            log.warn("记录链上事件异常, type={} keyId={} err={}", eventType, keyId, e.getMessage());
            return null;
        }
    }

    private boolean handleCreateReceipt(Long keyId, TransactionReceipt receipt) {
        if (!isReceiptStatusOk(keyId, receipt, "CREATE_KEY")) {
            return false;
        }

        List<KeyEvidence.UploadSuccessEventResponse> events = fiscoWrapper.getUploadSuccessEvents(receipt);
        if (events.isEmpty()) {
            // 走到这里说明交易成功却没有 UploadSuccess，最可能的原因是该 keyId
            // 在链上**已经存在**（uploadKey 里有 require(records[_keyId].keyId == 0,
            // "key exists")）。如实记下来：这条记录不会再被自动重试，
            // 因为重试永远不会成功 —— 需要人工确认链上那条是不是同一把密钥。
            logDetailFailure("Create chain sync missing UploadSuccess event (keyId already on chain?)", keyId, null);
            keyOperationRecordService.updateLatestResult(keyId, "CREATE", "2", "2",
                receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "MISSING_UPLOAD_EVENT");
            publishChainResult(keyId, "CREATE_KEY", "2", receipt.getTransactionHash(),
                parseBlockHeight(receipt.getBlockNumber()), "MISSING_UPLOAD_EVENT");
            return false;
        }

        Long blockHeight = parseBlockHeight(receipt.getBlockNumber());
        keymanageMapper.updateChainStatus(keyId, "1", receipt.getTransactionHash(), blockHeight);
        publishChainResult(keyId, "CREATE_KEY", "1", receipt.getTransactionHash(), blockHeight, null);
        return true;
    }

    public boolean processRotateChainSync(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyId() == null) {
            return false;
        }
        if (unsupportedLegacySync(keymanage, "UPDATE_KEY")) {
            return false;
        }

        try {
            String finalPA = calculatePA(keymanage);
            if (finalPA == null) {
                markFailed(keymanage.getKeyId());
                keyOperationRecordService.updateLatestResult(keymanage.getKeyId(), "UPDATE", "2", "2", null, null, "PA_CALC_FAILED");
                publishChainResult(keymanage.getKeyId(), "UPDATE_KEY", "2", null, null, "PA_CALC_FAILED");
                return false;
            }

            if (!ensureFiscoWrapper()) {
                markFailed(keymanage.getKeyId());
                keyOperationRecordService.updateLatestResult(keymanage.getKeyId(), "UPDATE", "2", "2", null, null, "FISCO_NOT_READY");
                publishChainResult(keymanage.getKeyId(), "UPDATE_KEY", "2", null, null, "FISCO_NOT_READY");
                return false;
            }

            TransactionReceipt receipt = fiscoWrapper.rotateKey(keymanage.getKeyId(), finalPA, keymanage.getVersion());
            return handleRotateReceipt(keymanage.getKeyId(), receipt);
        } catch (Exception e) {
            logDetailFailure("Rotate chain sync failed", keymanage.getKeyId(), e);
            markFailed(keymanage.getKeyId());
            keyOperationRecordService.updateLatestResult(keymanage.getKeyId(), "UPDATE", "2", "2", null, null, e.getClass().getSimpleName());
            publishChainResult(keymanage.getKeyId(), "UPDATE_KEY", "2", null, null, e.getClass().getSimpleName());
            return false;
        }
    }

    public boolean processRevokeChainSync(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyId() == null) {
            return false;
        }
        if (unsupportedLegacySync(keymanage, "REVOKE_KEY")) {
            return false;
        }

        try {
            if (!ensureFiscoWrapper()) {
                markFailed(keymanage.getKeyId());
                keyOperationRecordService.updateLatestResult(keymanage.getKeyId(), "REVOKE", "2", "2", null, null, "FISCO_NOT_READY");
                publishChainResult(keymanage.getKeyId(), "REVOKE_KEY", "2", null, null, "FISCO_NOT_READY");
                return false;
            }
            TransactionReceipt receipt = fiscoWrapper.changeKeyStatus(keymanage.getKeyId(), REVOKED_STATUS);
            return handleRevokeReceipt(keymanage.getKeyId(), receipt);
        } catch (Exception e) {
            logDetailFailure("Revoke chain sync failed", keymanage.getKeyId(), e);
            markFailed(keymanage.getKeyId());
            keyOperationRecordService.updateLatestResult(keymanage.getKeyId(), "REVOKE", "2", "2", null, null, e.getClass().getSimpleName());
            publishChainResult(keymanage.getKeyId(), "REVOKE_KEY", "2", null, null, e.getClass().getSimpleName());
            return false;
        }
    }

    private synchronized boolean ensureFiscoWrapper() {
        // 必须在缓存命中之前判；已有 wrapper 也不能绕过明确选择的 Fabric 后端。
        if (isFabricDidBackend()) {
            return false;
        }
        if (this.fiscoWrapper != null) {
            return true;
        }
        try {
            this.fiscoWrapper = new FiscoBcosWrapper(contractAddress, fiscoHost, fiscoPrivateKey);
            log.info("Lifecycle FISCO wrapper initialized lazily, contract: {}", contractAddress);
            return true;
        } catch (Exception e) {
            Thread.interrupted();
            this.fiscoWrapper = null;
            logDetailFailure("Failed to initialize lifecycle FISCO wrapper lazily", null, e);
            return false;
        }
    }

    private boolean handleRotateReceipt(Long keyId, TransactionReceipt receipt) {
        if (!isReceiptStatusOk(keyId, receipt, "UPDATE_KEY")) {
            return false;
        }

        List<KeyEvidence.KeyRotatedEventResponse> events = fiscoWrapper.getKeyRotatedEvents(receipt);
        if (events.isEmpty()) {
            logDetailFailure("Lifecycle rotate missing KeyRotated event", keyId, null);
            markFailed(keyId);
            keyOperationRecordService.updateLatestResult(keyId, "UPDATE", "2", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "MISSING_ROTATE_EVENT");
            publishChainResult(keyId, "UPDATE_KEY", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "MISSING_ROTATE_EVENT");
            return false;
        }

        KeyEvidence.KeyRotatedEventResponse lastEvent = events.get(events.size() - 1);
        if (lastEvent.status == null || lastEvent.status.intValue() != ACTIVE_STATUS) {
            logDetailFailure("Lifecycle rotate event status invalid, status=" + lastEvent.status, keyId, null);
            markFailed(keyId);
            keyOperationRecordService.updateLatestResult(keyId, "UPDATE", "2", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "INVALID_ROTATE_STATUS");
            publishChainResult(keyId, "UPDATE_KEY", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "INVALID_ROTATE_STATUS");
            return false;
        }

        Long blockHeight = parseBlockHeight(receipt.getBlockNumber());
        keymanageMapper.updateChainStatus(keyId, "1", receipt.getTransactionHash(), blockHeight);
        keyOperationRecordService.updateLatestResult(keyId, "UPDATE", "1", "1", receipt.getTransactionHash(), blockHeight, "更新成功，结果待用户接收");
        publishChainResult(keyId, "UPDATE_KEY", "1", receipt.getTransactionHash(), blockHeight, null);
        return true;
    }

    private boolean handleRevokeReceipt(Long keyId, TransactionReceipt receipt) {
        if (!isReceiptStatusOk(keyId, receipt, "REVOKE_KEY")) {
            return false;
        }

        List<KeyEvidence.StatusChangedEventResponse> events = fiscoWrapper.getStatusChangedEvents(receipt);
        if (events.isEmpty()) {
            logDetailFailure("Lifecycle revoke missing StatusChanged event", keyId, null);
            markFailed(keyId);
            keyOperationRecordService.updateLatestResult(keyId, "REVOKE", "2", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "MISSING_STATUS_EVENT");
            publishChainResult(keyId, "REVOKE_KEY", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "MISSING_STATUS_EVENT");
            return false;
        }

        KeyEvidence.StatusChangedEventResponse lastEvent = events.get(events.size() - 1);
        if (lastEvent.newStatus == null || lastEvent.newStatus.intValue() != REVOKED_STATUS) {
            logDetailFailure("Lifecycle revoke event status invalid, newStatus=" + lastEvent.newStatus, keyId, null);
            markFailed(keyId);
            keyOperationRecordService.updateLatestResult(keyId, "REVOKE", "2", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "INVALID_REVOKE_STATUS");
            publishChainResult(keyId, "REVOKE_KEY", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "INVALID_REVOKE_STATUS");
            return false;
        }

        Long blockHeight = parseBlockHeight(receipt.getBlockNumber());
        keymanageMapper.updateChainStatus(keyId, "1", receipt.getTransactionHash(), blockHeight);
        keyOperationRecordService.updateLatestResult(keyId, "REVOKE", "1", "1", receipt.getTransactionHash(), blockHeight, "回收成功，结果待用户接收");
        publishChainResult(keyId, "REVOKE_KEY", "1", receipt.getTransactionHash(), blockHeight, null);
        return true;
    }

    private boolean isReceiptStatusOk(Long keyId, TransactionReceipt receipt, String actionType) {
        if (receipt == null || !receipt.isStatusOK()) {
            if (receipt != null) {
                logDetailFailure("Lifecycle chain sync failed, status=" + receipt.getStatus() + ", message=" + receipt.getMessage(), keyId, null);
                keyOperationRecordService.updateLatestResult(keyId,
                    "UPDATE_KEY".equals(actionType) ? "UPDATE" : "REVOKE",
                    "2", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), receipt.getMessage());
                publishChainResult(keyId, actionType, "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), receipt.getMessage());
            } else {
                keyOperationRecordService.updateLatestResult(keyId,
                    "UPDATE_KEY".equals(actionType) ? "UPDATE" : "REVOKE",
                    "2", "2", null, null, "EMPTY_RECEIPT");
                publishChainResult(keyId, actionType, "2", null, null, "EMPTY_RECEIPT");
            }
            markFailed(keyId);
            return false;
        }

        return true;
    }

    private void markFailed(Long keyId) {
        keymanageMapper.updateChainStatus(keyId, "2", null, null);
    }

    private void publishChainResult(Long keyId, String actionType, String chainStatus, String chainHash, Long blockHeight, String errorMessage) {
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("key_id", keyId);
            payload.put("provider", getChainProvider());
            payload.put("chain_id", getChainId());
            payload.put("action_type", actionType);
            payload.put("chain_status", chainStatus);
            payload.put("chain_hash", chainHash);
            payload.put("block_height", blockHeight);
            payload.put("error_message", errorMessage);
            kafkaTemplate.send(chainResultTopic, String.valueOf(keyId), JSON.toJSONString(payload));
        } catch (Exception ex) {
            log.warn("发布生命周期上链结果失败, keyId={}", keyId, ex);
        }
    }

    private Long parseBlockHeight(String blockNumberStr) {
        if (blockNumberStr == null || blockNumberStr.isEmpty()) {
            return 0L;
        }
        try {
            if (blockNumberStr.startsWith("0x") || blockNumberStr.startsWith("0X")) {
                return new BigInteger(blockNumberStr.substring(2), 16).longValue();
            }
            return Long.valueOf(blockNumberStr);
        } catch (Exception e) {
            return 0L;
        }
    }

    /**
     * 计算无证书密钥的**加密目标点** {@code P_A}（16 进制、未压缩、130 字符、`04` 开头）。
     *
     * <h2>这是全系统唯一一份 P_A 推导，切勿另写第二份</h2>
     * {@code P_A} 是用户**实际可解**的公钥点：客户端持有
     * {@code d_A = (t_A + u) mod n}，而 {@code d_A·G = W_A + λ·P_pub}。
     * 因此任何人若拿 {@code key_value} 里的 {@code finalPublicKey}（= {@code W_A}）
     * 去加密，做出来的信封**谁都打不开** —— 连用户自己也不行。
     * 这正是计划 §3.2.3 用实验纠正过的那个错误，也是本方法被提为 public、
     * 由 {@link com.ruoyi.updatedel.service.UserPublicKeyService} 对外统一提供的原因：
     * 分发模块必须拿到**这个**点，而不是 {@code key_value} 里的任何一个字段。
     *
     * <p>两条分支：
     * <ul>
     *   <li><b>SM2</b>：{@code P_A = W_A + λ·P_pub}，其中
     *       {@code λ = SM3(W_A_x || W_A_y || H_A)}，{@code P_pub = ms·G}。
     *       <b>ms 必须按记录自己的 {@code ms_key_id} 取</b>，否则轮换过 ms 之后
     *       历史记录会算出与链上存证不一致的点。</li>
     *   <li><b>SSCL</b>：{@code P_A = u_A + (e_A·m)·G}，{@code e_A} 直接取自记录里存的
     *       {@code SSCLEA} —— 它已经把 ms 的影响包含在内，所以这一支**不需要 ms**，
     *       也天然不受轮换影响。</li>
     * </ul>
     *
     * @return 计算失败（缺字段、点不在曲线上、算法不支持等）时返回 {@code null}，
     *         调用方必须把它当作错误处理，**不得**回退到 {@code finalPublicKey}
     */
    public String calculatePA(Keymanage keymanage) {
        try {
            if (keymanage.getKeyValue() == null) {
                return null;
            }

            JSONObject keyValue = JSON.parseObject(keymanage.getKeyValue());
            String ssclKey = keyValue.getString("SSCLKey");
            if (ssclKey != null) {
                return calculateSSCLPublicKey(keymanage, keyValue, ssclKey);
            }

            String wA = keyValue.getString("finalPublicKey");
            if (wA == null) {
                wA = keyValue.getString("publicKey");
            }
            if (wA == null) {
                return null;
            }
            return calculateSM2FinalPublicKey(keymanage.getUserName(), wA, keymanage.getMsKeyId());
        } catch (Exception e) {
            logDetailFailure("Failed to calculate PA", keymanage.getKeyId(), e);
            return null;
        }
    }

    private String calculateSSCLPublicKey(Keymanage keymanage, JSONObject keyValue, String ssclKey) {
        String eAHex = keyValue.getString("SSCLEA");
        if (eAHex == null || eAHex.length() != 64) {
            logDetailFailure("SSCL rotate chain sync missing SSCLEA", keymanage.getKeyId(), null);
            return null;
        }
        String ua = keymanage.getUa();
        if (ua == null || ua.length() != 130 || !ua.startsWith("04")) {
            logDetailFailure("Invalid lifecycle uA for SSCL chain sync", keymanage.getKeyId(), null);
            return null;
        }

        org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve = new org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve();
        BigInteger n = curve.getOrder();
        ECPoint g = curve.createPoint(SM2_GX, SM2_GY);
        BigInteger m = new BigInteger(ssclKey.substring(2, 66), 16);
        BigInteger eA = new BigInteger(eAHex, 16);
        ECPoint uA = parseUncompressedPoint(curve, ua, "uA");
        if (uA == null) {
            return null;
        }

        BigInteger scalar = eA.multiply(m).mod(n);
        ECPoint pa = uA.add(g.multiply(scalar).normalize()).normalize();
        return Hex.toHexString(pa.getEncoded(false)).toUpperCase();
    }

    private String calculateSM2FinalPublicKey(String userId, String uAStr, String msKeyId) {
        org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve = new org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve();
        BigInteger n = curve.getOrder();
        ECPoint g = curve.createPoint(SM2_GX, SM2_GY);
        // 按**记录自己那一版**的 ms 取密钥，而不是当前启用版本。
        // 这是"轮换 ms 不再破坏历史可审计性"的关键一步：
        // 用启用版本算出来的 P_A 与链上旧存证必然不一致，历史记录会当场变得无法验证。
        // msKeyId 为空表示早期记录 → KgcMasterSecret 内部按 ms_v1 处理。
        BigInteger ms = new BigInteger(KgcMasterSecret.getById(msKeyId), 16);
        ECPoint pPub = g.multiply(ms).normalize();

        if (uAStr.startsWith("04")) {
            uAStr = uAStr.substring(2);
        }
        ECPoint wA = parseUncompressedPoint(curve, "04" + uAStr, "wA");
        if (wA == null) {
            return null;
        }

        org.bouncycastle.crypto.digests.SM3Digest digest = new org.bouncycastle.crypto.digests.SM3Digest();
        int entlen = userId.getBytes().length * 8;
        digest.update((byte) (entlen >> 8));
        digest.update((byte) entlen);
        digest.update(userId.getBytes(), 0, userId.getBytes().length);
        byte[] a = to32Bytes(curve.getA().toBigInteger());
        byte[] b = to32Bytes(curve.getB().toBigInteger());
        byte[] gx = to32Bytes(g.getAffineXCoord().toBigInteger());
        byte[] gy = to32Bytes(g.getAffineYCoord().toBigInteger());
        byte[] pPubX = to32Bytes(pPub.getAffineXCoord().toBigInteger());
        byte[] pPubY = to32Bytes(pPub.getAffineYCoord().toBigInteger());
        digest.update(a, 0, 32);
        digest.update(b, 0, 32);
        digest.update(gx, 0, 32);
        digest.update(gy, 0, 32);
        digest.update(pPubX, 0, 32);
        digest.update(pPubY, 0, 32);

        byte[] hA = new byte[32];
        digest.doFinal(hA, 0);

        digest.reset();
        byte[] waX = to32Bytes(wA.getAffineXCoord().toBigInteger());
        byte[] waY = to32Bytes(wA.getAffineYCoord().toBigInteger());
        digest.update(waX, 0, 32);
        digest.update(waY, 0, 32);
        digest.update(hA, 0, 32);

        byte[] lambdaBytes = new byte[32];
        digest.doFinal(lambdaBytes, 0);
        BigInteger lambda = new BigInteger(1, lambdaBytes).mod(n);
        ECPoint pa = wA.add(pPub.multiply(lambda)).normalize();
        return Hex.toHexString(pa.getEncoded(false)).toUpperCase();
    }

    private ECPoint parseUncompressedPoint(org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve, String pointHex, String fieldName) {
        if (pointHex == null || pointHex.length() != 130 || !pointHex.startsWith("04")) {
            if (chainDetailLogEnabled) {
                log.warn("{} format invalid: {}", fieldName, pointHex);
            }
            return null;
        }

        BigInteger x = new BigInteger(pointHex.substring(2, 66), 16);
        BigInteger y = new BigInteger(pointHex.substring(66, 130), 16);
        ECPoint point = curve.createPoint(x, y);
        return point.isValid() ? point : null;
    }

    private byte[] to32Bytes(BigInteger value) {
        byte[] source = value.toByteArray();
        if (source.length == 32) {
            return source;
        }
        byte[] target = new byte[32];
        if (source.length > 32) {
            System.arraycopy(source, source.length - 32, target, 0, 32);
        } else {
            System.arraycopy(source, 0, target, 32 - source.length, source.length);
        }
        return target;
    }

    private void logDetailFailure(String message, Long keyId, Exception e) {
        if (!chainDetailLogEnabled) {
            return;
        }
        if (e == null) {
            log.warn("{}, keyId={}", message, keyId);
        } else {
            log.warn("{}, keyId={}", message, keyId, e);
        }
    }

    private static class FiscoBcosWrapper {
        private final String contractAddress;
        private final String fiscoHost;
        private final String privateKeyHex;
        private KeyEvidence keyEvidence;
        private Client client;

        private FiscoBcosWrapper(String contractAddress, String fiscoHost, String privateKeyHex) throws Exception {
            this.contractAddress = contractAddress;
            this.fiscoHost = fiscoHost;
            this.privateKeyHex = privateKeyHex;
            init();
        }

        private void init() throws Exception {
            File configFile = new File("config-fisco.toml");
            if (!configFile.exists()) {
                configFile = new File("/app/config-fisco.toml");
            }
            if (!configFile.exists()) {
                throw new RuntimeException("FISCO config file not found");
            }

            String configContent = new String(java.nio.file.Files.readAllBytes(configFile.toPath()));
            try {
                String realIp = java.net.InetAddress.getByName(fiscoHost).getHostAddress();
                configContent = configContent.replace(fiscoHost, realIp);
            } catch (Exception ignored) {
            }

            File tempConfigFile = File.createTempFile("fisco-config-resolved", ".toml");
            java.nio.file.Files.write(tempConfigFile.toPath(), configContent.getBytes());

            BcosSDK sdk = BcosSDK.build(tempConfigFile.getAbsolutePath());
            this.client = sdk.getClient(1);
            CryptoKeyPair cryptoKeyPair = createConfiguredKeyPair();
            if (contractAddress == null || "0x0000000000000000000000000000000000000000".equals(contractAddress)) {
                throw new RuntimeException("Contract address not configured");
            }
            this.keyEvidence = KeyEvidence.load(contractAddress, client, cryptoKeyPair);
        }

        private TransactionReceipt rotateKey(Long keyId, String newPubKey, Integer newVersion) {
            return keyEvidence.rotateKey(BigInteger.valueOf(keyId), newPubKey, BigInteger.valueOf(newVersion == null ? 1 : newVersion));
        }

        /**
         * 把一条新密钥登记到链上（文档 §8.6 的 KEY_CREATED 事件）。
         *
         * <p><b>这不是可选动作</b>：契约里的 {@code rotateKey} 与
         * {@code changeKeyStatus} 都以 {@code require(k.keyId != 0)} 开头 ——
         * **记录必须先 uploadKey 存在**，否则那两笔调用在链上直接 revert。
         *
         * <p>在此之前本服务**从未调用过** uploadKey，于是更新与回收虽然能发出交易、
         * 拿回一个“成功”的回执，链上却没有任何事件 —— 因为合约里的 require
         * 在写事件之前就失败了。表现为 {@code MISSING_ROTATE_EVENT} /
         * {@code MISSING_STATUS_EVENT} 这类“交易成功但没有事件”的结论，
         * 看上去像事件解析出了 bug，实际是记录压根不存在。
         *
         * @param pubKey 上链的是**公开材料**：SM2/SSCL 传公钥点，
         *               Kyber/Falcon 传公钥摘要。绝不上传私钥或节点侧秘密 u。
         */
        private TransactionReceipt uploadKey(Long keyId, String username, String pubKey,
                                             String algo, String usage, Boolean isAutoUpdate,
                                             Integer version) {
            return keyEvidence.uploadKey(
                BigInteger.valueOf(keyId),
                username == null ? "" : username,
                pubKey == null ? "" : pubKey,
                algo == null ? "" : algo,
                usage == null ? "" : usage,
                isAutoUpdate != null && isAutoUpdate,
                BigInteger.valueOf(version == null ? 1 : version));
        }

        private List<KeyEvidence.UploadSuccessEventResponse> getUploadSuccessEvents(TransactionReceipt receipt) {
            return keyEvidence.getUploadSuccessEvents(receipt);
        }

        private TransactionReceipt recordEvent(String eventType, BigInteger keyId, BigInteger version,
                                               String nodeId, String publicMaterialHash) {
            return keyEvidence.recordEvent(eventType, keyId, version, nodeId, publicMaterialHash);
        }

        private List<KeyEvidence.KeyLifecycleEventEventResponse> getKeyLifecycleEvents(TransactionReceipt receipt) {
            return keyEvidence.getKeyLifecycleEventEvents(receipt);
        }

        private TransactionReceipt changeKeyStatus(Long keyId, int newStatus) {
            return keyEvidence.changeKeyStatus(BigInteger.valueOf(keyId), BigInteger.valueOf(newStatus));
        }

        private List<KeyEvidence.KeyRotatedEventResponse> getKeyRotatedEvents(TransactionReceipt receipt) {
            return keyEvidence.getKeyRotatedEvents(receipt);
        }

        private List<KeyEvidence.StatusChangedEventResponse> getStatusChangedEvents(TransactionReceipt receipt) {
            return keyEvidence.getStatusChangedEvents(receipt);
        }

        private CryptoKeyPair createConfiguredKeyPair() {
            if (privateKeyHex != null && !privateKeyHex.trim().isEmpty()) {
                return client.getCryptoSuite().createKeyPair(privateKeyHex.trim());
            }
            log.warn("Lifecycle FISCO private key not configured, using ephemeral account");
            return client.getCryptoSuite().createKeyPair();
        }
    }
}
