package com.ruoyi.generate.service.impl;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.generate.contracts.KeyEvidence;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateChainService;
import com.ruoyi.generate.service.GenerateKeyService;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;
import org.fisco.bcos.sdk.BcosSDK;
import org.fisco.bcos.sdk.client.Client;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;
import org.fisco.bcos.sdk.model.TransactionReceipt;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.io.File;
import java.math.BigInteger;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 区块链上链服务实现
 * 负责将密钥上链到 FISCO BCOS 区块链
 */
@Service
public class GenerateChainServiceImpl implements GenerateChainService {

    private static final Logger log = LoggerFactory.getLogger(GenerateChainServiceImpl.class);
    private static final BigInteger SM2_GX = new BigInteger("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7", 16);
    private static final BigInteger SM2_GY = new BigInteger("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0", 16);

    @Autowired
    private GenerateKeyService generateKeyService;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Value("${fisco.contract-address:0x0000000000000000000000000000000000000000}")
    private String contractAddress;

    @Value("${fisco.host:fisco-node}")
    private String fiscoHost;

    @Value("${fisco.private-key:}")
    private String fiscoPrivateKey;

    @Value("${kms.kafka.chain-result-topic:key_chain_result}")
    private String chainResultTopic;

    private FiscoBcosWrapper fiscoWrapper;

    @PostConstruct
    public void init() {
        // 上链客户端改为懒初始化，避免 FISCO SDK 在 Spring 启动阶段连接失败时打断整个服务启动。
        this.fiscoWrapper = null;
        log.info("FISCO BCOS wrapper will initialize lazily when chain sync is triggered");
    }

    @Override
    public boolean processChainSync(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyId() == null) {
            log.error("Invalid keymanage for chain sync");
            return false;
        }

        try {
            // 1. 计算最终公钥 PA
            String finalPA = calculatePA(keymanage);
            if (finalPA == null) {
                log.error("KeyId: {} 公钥计算失败", keymanage.getKeyId());
                generateKeyService.updateChainStatus(keymanage.getKeyId(), "2", null, null);
                publishChainResult(keymanage.getKeyId(), "ENROLL_KEY", "2", null, null, "PA_CALC_FAILED");
                return false;
            }

            // 2. 执行上链
            if (!ensureFiscoWrapper()) {
                log.error("FISCO wrapper not initialized");
                generateKeyService.updateChainStatus(keymanage.getKeyId(), "2", null, null);
                publishChainResult(keymanage.getKeyId(), "ENROLL_KEY", "2", null, null, "FISCO_NOT_READY");
                return false;
            }

            TransactionReceipt receipt = fiscoWrapper.uploadKey(
                    keymanage.getKeyId(),
                    keymanage.getUserName(),
                    finalPA,
                    keymanage.getEncrytName(),
                    keymanage.getKeyUse(),
                    isAutoUpdateEnabled(keymanage.getAutoUpdate()),
                    keymanage.getVersion()
            );

            // 3. 处理结果
            return handleUploadReceipt(keymanage.getKeyId(), receipt);

        } catch (Exception e) {
            log.error("KeyId: {} 上链异常", keymanage.getKeyId(), e);
            generateKeyService.updateChainStatus(keymanage.getKeyId(), "2", null, null);
            publishChainResult(keymanage.getKeyId(), "ENROLL_KEY", "2", null, null, e.getClass().getSimpleName());
            return false;
        }
    }

    @Override
    public GenerateChainService.ChainSyncStatus getChainStatus(Long keyId) {
        Keymanage key = generateKeyService.selectKeyById(keyId);
        if (key == null) {
            return null;
        }
        GenerateChainService.ChainSyncStatus status = new GenerateChainService.ChainSyncStatus();
        status.setKeyId(key.getKeyId());
        status.setChainStatus(key.getChainStatus());
        status.setChainHash(key.getChainHash());
        status.setBlockHeight(key.getBlockHeight());
        status.setStatus(key.getStatus());
        return status;
    }

    private synchronized boolean ensureFiscoWrapper() {
        if (this.fiscoWrapper != null) {
            return true;
        }
        try {
            this.fiscoWrapper = new FiscoBcosWrapper(contractAddress, fiscoHost, fiscoPrivateKey);
            log.info("FISCO BCOS wrapper initialized lazily, contract: {}", contractAddress);
            return true;
        } catch (Exception e) {
            Thread.interrupted();
            this.fiscoWrapper = null;
            log.error("Failed to initialize FISCO BCOS wrapper lazily", e);
            return false;
        }
    }

    private boolean handleUploadReceipt(Long keyId, TransactionReceipt receipt) {
        if (receipt == null) {
            generateKeyService.updateChainStatus(keyId, "2", null, null);
            publishChainResult(keyId, "ENROLL_KEY", "2", null, null, "EMPTY_RECEIPT");
            return false;
        }

        if (!receipt.isStatusOK()) {
            log.error("KeyId: {} 上链失败，状态码: {}, 信息: {}",
                    keyId, receipt.getStatus(), receipt.getMessage());
            generateKeyService.updateChainStatus(keyId, "2", null, null);
            publishChainResult(keyId, "ENROLL_KEY", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), receipt.getMessage());
            return false;
        }

        List<KeyEvidence.UploadSuccessEventResponse> events = fiscoWrapper.getUploadSuccessEvents(receipt);
        if (events.isEmpty()) {
            log.error("KeyId: {} 上链交易缺少 UploadSuccess 事件，按失败处理", keyId);
            generateKeyService.updateChainStatus(keyId, "2", null, null);
            publishChainResult(keyId, "ENROLL_KEY", "2", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()), "MISSING_UPLOAD_EVENT");
            return false;
        }

        String txHash = receipt.getTransactionHash();
        Long blockHeight = parseBlockHeight(receipt.getBlockNumber());

        generateKeyService.updateChainStatus(keyId, "1", txHash, blockHeight);
        publishChainResult(keyId, "ENROLL_KEY", "1", txHash, blockHeight, null);
        log.info("KeyId: {} 上链成功，txHash: {}, blockHeight: {}", keyId, txHash, blockHeight);
        return true;
    }

    private void publishChainResult(Long keyId, String actionType, String chainStatus, String chainHash, Long blockHeight, String errorMessage) {
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("key_id", keyId);
            payload.put("action_type", actionType);
            payload.put("chain_status", chainStatus);
            payload.put("chain_hash", chainHash);
            payload.put("block_height", blockHeight);
            payload.put("error_message", errorMessage);
            kafkaTemplate.send(chainResultTopic, String.valueOf(keyId), JSON.toJSONString(payload));
        } catch (Exception ex) {
            log.warn("发布生成系统上链结果失败, keyId={}", keyId, ex);
        }
    }

    private Long parseBlockHeight(String blockNumberStr) {
        if (blockNumberStr == null || blockNumberStr.isEmpty()) return 0L;
        try {
            if (blockNumberStr.startsWith("0x") || blockNumberStr.startsWith("0X")) {
                return new BigInteger(blockNumberStr.substring(2), 16).longValue();
            }
            return Long.valueOf(blockNumberStr);
        } catch (Exception e) {
            return 0L;
        }
    }

    private boolean isAutoUpdateEnabled(String autoUpdate) {
        if (autoUpdate == null) {
            return false;
        }
        String value = autoUpdate.trim();
        return "1".equals(value)
                || "true".equalsIgnoreCase(value)
                || "enabled".equalsIgnoreCase(value);
    }

    /**
     * 计算最终公钥 PA
     */
    private String calculatePA(Keymanage km) {
        try {
            if (km.getKeyValue() == null) return null;

            if (!"无证书非对称加密".equals(km.getEncrytType())) {
                return null;
            }

            JSONObject kv = JSON.parseObject(km.getKeyValue());

            String ssclKey = kv.getString("SSCLKey");
            if (ssclKey != null) {
                return calculateSSCLPublicKey(km, kv, ssclKey);
            }

            // SM2 算法分支
            String wA = kv.getString("finalPublicKey");
            if (wA == null) wA = kv.getString("publicKey");

            if (wA == null) return null;

            // 使用 SM2 计算最终公钥
            return calculateSM2FinalPublicKey(km.getUserName(), wA);

        } catch (Exception e) {
            log.error("计算 PA 异常", e);
            return null;
        }
    }

    /**
     * SSCL 无证书公钥计算。
     * 公式: PA = uA + (eA * m mod n) * G
     *
     * eA 由 Go 生成服务随 SSCLKey 一并写入 keyValue，避免分布式部署下的随机参数不一致。
     */
    private String calculateSSCLPublicKey(Keymanage km, JSONObject kv, String ssclKey) {
        try {
            if (ssclKey.length() != 130 || !ssclKey.startsWith("04")) {
                log.error("SSCLKey 格式无效: {}", ssclKey);
                return null;
            }

            String eAHex = kv.getString("SSCLEA");
            if (eAHex == null || eAHex.length() != 64) {
                log.error("SSCL 上链缺少 SSCLEA 参数, keyId={}", km.getKeyId());
                return null;
            }

            String uAStr = km.getuA();
            if (uAStr == null || uAStr.length() != 130 || !uAStr.startsWith("04")) {
                log.error("用户部分公钥 uA 格式无效: {}", uAStr);
                return null;
            }

            org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve =
                    new org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve();
            BigInteger n = curve.getOrder();
            ECPoint g = curve.createPoint(SM2_GX, SM2_GY);

            BigInteger m = new BigInteger(ssclKey.substring(2, 66), 16);
            BigInteger eA = new BigInteger(eAHex, 16);
            ECPoint uA = parseUncompressedPoint(curve, uAStr, "uA");
            if (uA == null) {
                return null;
            }

            BigInteger scalar = eA.multiply(m).mod(n);
            ECPoint part2 = g.multiply(scalar).normalize();
            ECPoint pa = uA.add(part2).normalize();

            return Hex.toHexString(pa.getEncoded(false)).toUpperCase();
        } catch (Exception e) {
            log.error("SSCL 公钥计算异常", e);
            return null;
        }
    }

    /**
     * SM2 无证书公钥计算
     */
    private String calculateSM2FinalPublicKey(String userId, String uAStr) {
        try {
            org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve =
                    new org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve();
            BigInteger n = curve.getOrder();

            ECPoint G = curve.createPoint(SM2_GX, SM2_GY);

            String msHex = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";
            BigInteger ms = new BigInteger(msHex, 16);
            ECPoint PPub = G.multiply(ms).normalize();

            // 解析 WA
            if (uAStr.startsWith("04")) {
                uAStr = uAStr.substring(2);
            }
            ECPoint WA = parseUncompressedPoint(curve, "04" + uAStr, "wA");
            if (WA == null) {
                return null;
            }

            // SM3 digest 计算
            org.bouncycastle.crypto.digests.SM3Digest digest = new org.bouncycastle.crypto.digests.SM3Digest();

            int entlen = userId.getBytes().length * 8;
            digest.update((byte) (entlen >> 8));
            digest.update((byte) entlen);
            digest.update(userId.getBytes(), 0, userId.getBytes().length);
            byte[] a = to32Bytes(curve.getA().toBigInteger());
            byte[] b = to32Bytes(curve.getB().toBigInteger());
            byte[] gx = to32Bytes(G.getAffineXCoord().toBigInteger());
            byte[] gy = to32Bytes(G.getAffineYCoord().toBigInteger());
            byte[] pPubX = to32Bytes(PPub.getAffineXCoord().toBigInteger());
            byte[] pPubY = to32Bytes(PPub.getAffineYCoord().toBigInteger());
            digest.update(a, 0, 32);
            digest.update(b, 0, 32);
            digest.update(gx, 0, 32);
            digest.update(gy, 0, 32);
            digest.update(pPubX, 0, 32);
            digest.update(pPubY, 0, 32);

            byte[] HA = new byte[32];
            digest.doFinal(HA, 0);

            // lambda 计算
            digest.reset();
            byte[] waX = to32Bytes(WA.getAffineXCoord().toBigInteger());
            byte[] waY = to32Bytes(WA.getAffineYCoord().toBigInteger());
            digest.update(waX, 0, 32);
            digest.update(waY, 0, 32);
            digest.update(HA, 0, 32);

            byte[] lambdaBytes = new byte[32];
            digest.doFinal(lambdaBytes, 0);
            BigInteger lambda = new BigInteger(1, lambdaBytes).mod(n);

            // PA = WA + [lambda]PPub
            ECPoint temp = PPub.multiply(lambda);
            ECPoint PA = WA.add(temp).normalize();

            return Hex.toHexString(PA.getEncoded(false)).toUpperCase();

        } catch (Exception e) {
            log.error("SM2 公钥计算异常", e);
            return null;
        }
    }

    private ECPoint parseUncompressedPoint(org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve,
                                           String pointHex,
                                           String fieldName) {
        if (pointHex == null || pointHex.length() != 130 || !pointHex.startsWith("04")) {
            log.error("{} 格式无效: {}", fieldName, pointHex);
            return null;
        }

        BigInteger x = new BigInteger(pointHex.substring(2, 66), 16);
        BigInteger y = new BigInteger(pointHex.substring(66, 130), 16);
        ECPoint point = curve.createPoint(x, y);
        if (!point.isValid()) {
            log.error("{} 不在曲线上", fieldName);
            return null;
        }
        return point;
    }

    private byte[] to32Bytes(BigInteger n) {
        byte[] b = n.toByteArray();
        if (b.length == 32) return b;
        byte[] res = new byte[32];
        if (b.length > 32) {
            System.arraycopy(b, b.length - 32, res, 0, 32);
        } else {
            System.arraycopy(b, 0, res, 32 - b.length, b.length);
        }
        return res;
    }

    /**
     * FISCO BCOS 包装类
     */
    private static class FiscoBcosWrapper {
        private final String contractAddress;
        private final String fiscoHost;
        private final String privateKeyHex;
        private KeyEvidence keyEvidence;
        private Client client;

        public FiscoBcosWrapper(String contractAddress, String fiscoHost, String privateKeyHex) throws Exception {
            this.contractAddress = contractAddress;
            this.fiscoHost = fiscoHost;
            this.privateKeyHex = privateKeyHex;
            init();
        }

        private void init() throws Exception {
            log.info("Initializing FISCO BCOS SDK...");
            File configFile = new File("config-fisco.toml");
            if (!configFile.exists()) {
                configFile = new File("/app/config-fisco.toml");
            }
            if (!configFile.exists()) {
                throw new RuntimeException("FISCO config file not found");
            }

            String configContent = new String(java.nio.file.Files.readAllBytes(configFile.toPath()));

            try {
                java.net.InetAddress address = java.net.InetAddress.getByName(fiscoHost);
                String realIp = address.getHostAddress();
                configContent = configContent.replace(fiscoHost, realIp);
            } catch (Exception e) {
                log.warn("DNS resolution failed, using original config");
            }

            File tempConfigFile = File.createTempFile("fisco-config-resolved", ".toml");
            java.nio.file.Files.write(tempConfigFile.toPath(), configContent.getBytes());

            BcosSDK sdk = BcosSDK.build(tempConfigFile.getAbsolutePath());
            this.client = sdk.getClient(1);
            CryptoKeyPair cryptoKeyPair = createConfiguredKeyPair();
            log.info("FISCO SDK initialized, account: {}", cryptoKeyPair.getAddress());

            if (contractAddress != null && !contractAddress.equals("0x0000000000000000000000000000000000000000")) {
                this.keyEvidence = KeyEvidence.load(contractAddress, client, cryptoKeyPair);
                log.info("KeyEvidence contract loaded, address: {}", contractAddress);
            } else {
                throw new RuntimeException("Contract address not configured");
            }
        }

        public TransactionReceipt uploadKey(Long keyId, String user, String pubKey,
                                              String algo, String usage, boolean autoUpdate, Integer version) {
            checkReady();
            try {
                log.info("uploadKey calling contract: keyId={}, user={}, pubKey={}, algo={}", keyId, user, pubKey, algo);
                BigInteger bKeyId = BigInteger.valueOf(keyId);
                BigInteger bVersion = BigInteger.valueOf(version);
                return keyEvidence.uploadKey(bKeyId, user, pubKey, algo, usage, autoUpdate, bVersion);
            } catch (Exception e) {
                log.error("uploadKey contract call failed", e);
                throw new RuntimeException("区块链[uploadKey]调用失败", e);
            }
        }

        public List<KeyEvidence.UploadSuccessEventResponse> getUploadSuccessEvents(TransactionReceipt receipt) {
            checkReady();
            return keyEvidence.getUploadSuccessEvents(receipt);
        }

        private CryptoKeyPair createConfiguredKeyPair() {
            if (privateKeyHex != null && !privateKeyHex.trim().isEmpty()) {
                return client.getCryptoSuite().createKeyPair(privateKeyHex.trim());
            }
            log.warn("FISCO private key not configured, using ephemeral account");
            return client.getCryptoSuite().createKeyPair();
        }

        private void checkReady() {
            if (this.keyEvidence == null) {
                throw new RuntimeException("合约未加载！请检查 application.yml 中的 fisco.contract-address 配置是否正确。");
            }
        }
    }
}
