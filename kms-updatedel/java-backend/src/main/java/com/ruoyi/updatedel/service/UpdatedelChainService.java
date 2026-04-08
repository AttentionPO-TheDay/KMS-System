package com.ruoyi.updatedel.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.updatedel.contracts.KeyEvidence;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.repository.KeymanageRepository;
import java.io.File;
import java.math.BigInteger;
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
import org.springframework.stereotype.Service;

@Service
public class UpdatedelChainService {

    private static final Logger log = LoggerFactory.getLogger(UpdatedelChainService.class);
    private static final BigInteger SM2_GX = new BigInteger("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7", 16);
    private static final BigInteger SM2_GY = new BigInteger("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0", 16);
    private static final int REVOKED_STATUS = 3;

    private final KeymanageRepository keymanageRepository;

    @Value("${fisco.contract-address:0x0000000000000000000000000000000000000000}")
    private String contractAddress;

    private FiscoBcosWrapper fiscoWrapper;

    public UpdatedelChainService(KeymanageRepository keymanageRepository) {
        this.keymanageRepository = keymanageRepository;
    }

    @PostConstruct
    public void init() {
        try {
            this.fiscoWrapper = new FiscoBcosWrapper(contractAddress);
            log.info("Lifecycle FISCO wrapper initialized, contract: {}", contractAddress);
        } catch (Exception e) {
            log.error("Failed to initialize lifecycle FISCO wrapper", e);
        }
    }

    public boolean processRotateChainSync(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyId() == null) {
            return false;
        }

        try {
            String finalPA = calculatePA(keymanage);
            if (finalPA == null) {
                markFailed(keymanage.getKeyId());
                return false;
            }

            if (fiscoWrapper == null) {
                markFailed(keymanage.getKeyId());
                return false;
            }

            TransactionReceipt receipt = fiscoWrapper.rotateKey(keymanage.getKeyId(), finalPA, keymanage.getVersion());
            return handleTransactionReceipt(keymanage.getKeyId(), receipt);
        } catch (Exception e) {
            log.error("Rotate chain sync failed, keyId={}", keymanage.getKeyId(), e);
            markFailed(keymanage.getKeyId());
            return false;
        }
    }

    public boolean processRevokeChainSync(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyId() == null) {
            return false;
        }

        try {
            if (fiscoWrapper == null) {
                markFailed(keymanage.getKeyId());
                return false;
            }
            TransactionReceipt receipt = fiscoWrapper.changeKeyStatus(keymanage.getKeyId(), REVOKED_STATUS);
            return handleTransactionReceipt(keymanage.getKeyId(), receipt);
        } catch (Exception e) {
            log.error("Revoke chain sync failed, keyId={}", keymanage.getKeyId(), e);
            markFailed(keymanage.getKeyId());
            return false;
        }
    }

    private boolean handleTransactionReceipt(Long keyId, TransactionReceipt receipt) {
        if (receipt == null || !receipt.isStatusOK()) {
            if (receipt != null) {
                log.error("Lifecycle chain sync failed, keyId={}, status={}, message={}", keyId, receipt.getStatus(), receipt.getMessage());
            }
            markFailed(keyId);
            return false;
        }

        keymanageRepository.updateChainStatus(keyId, "1", receipt.getTransactionHash(), parseBlockHeight(receipt.getBlockNumber()));
        return true;
    }

    private void markFailed(Long keyId) {
        keymanageRepository.updateChainStatus(keyId, "2", null, null);
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

    private String calculatePA(Keymanage keymanage) {
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
            return calculateSM2FinalPublicKey(keymanage.getUserName(), wA);
        } catch (Exception e) {
            log.error("Failed to calculate PA, keyId={}", keymanage.getKeyId(), e);
            return null;
        }
    }

    private String calculateSSCLPublicKey(Keymanage keymanage, JSONObject keyValue, String ssclKey) {
        String eAHex = keyValue.getString("SSCLEA");
        if (eAHex == null || eAHex.length() != 64) {
            log.error("SSCL rotate chain sync missing SSCLEA, keyId={}", keymanage.getKeyId());
            return null;
        }
        String ua = keymanage.getUa();
        if (ua == null || ua.length() != 130 || !ua.startsWith("04")) {
            log.error("Invalid lifecycle uA for SSCL chain sync, keyId={}", keymanage.getKeyId());
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

    private String calculateSM2FinalPublicKey(String userId, String uAStr) {
        org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve curve = new org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve();
        BigInteger n = curve.getOrder();
        ECPoint g = curve.createPoint(SM2_GX, SM2_GY);
        BigInteger ms = new BigInteger("6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9", 16);
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
            log.error("{} format invalid: {}", fieldName, pointHex);
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

    private static class FiscoBcosWrapper {
        private final String contractAddress;
        private KeyEvidence keyEvidence;

        private FiscoBcosWrapper(String contractAddress) throws Exception {
            this.contractAddress = contractAddress;
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
                String realIp = java.net.InetAddress.getByName("fisco-node").getHostAddress();
                configContent = configContent.replace("fisco-node", realIp);
            } catch (Exception ignored) {
            }

            File tempConfigFile = File.createTempFile("fisco-config-resolved", ".toml");
            java.nio.file.Files.write(tempConfigFile.toPath(), configContent.getBytes());

            BcosSDK sdk = BcosSDK.build(tempConfigFile.getAbsolutePath());
            Client client = sdk.getClient(1);
            CryptoKeyPair cryptoKeyPair = client.getCryptoSuite().createKeyPair();
            if (contractAddress == null || "0x0000000000000000000000000000000000000000".equals(contractAddress)) {
                throw new RuntimeException("Contract address not configured");
            }
            this.keyEvidence = KeyEvidence.load(contractAddress, client, cryptoKeyPair);
        }

        private TransactionReceipt rotateKey(Long keyId, String newPubKey, Integer newVersion) {
            return keyEvidence.rotateKey(BigInteger.valueOf(keyId), newPubKey, BigInteger.valueOf(newVersion == null ? 1 : newVersion));
        }

        private TransactionReceipt changeKeyStatus(Long keyId, int newStatus) {
            return keyEvidence.changeKeyStatus(BigInteger.valueOf(keyId), BigInteger.valueOf(newStatus));
        }
    }
}
