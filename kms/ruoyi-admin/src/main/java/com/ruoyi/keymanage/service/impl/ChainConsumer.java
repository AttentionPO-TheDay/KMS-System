package com.ruoyi.keymanage.service.impl;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.keymanage.domain.ChainSyncEvent;
import com.ruoyi.keymanage.domain.Keymanage;
import com.ruoyi.keymanage.mapper.KeymanageMapper;
import com.ruoyi.keymanage.service.impl.generator.SSCLGenerator;
// import com.ruoyi.keymanage.service.ISm2CalculationService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.encoders.Hex;
import org.fisco.bcos.sdk.model.TransactionReceipt;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.math.BigInteger;
import java.util.List;

@Component
public class ChainConsumer {

    private static final Logger log = LoggerFactory.getLogger(ChainConsumer.class);

    @Autowired
    private Sm2CalculationService sm2Service;

    @Autowired
    private SSCLGenerator ssclGen;

    @Autowired
    private FiscoBcosService fiscoService;

    @Autowired
    private KeymanageMapper keymanageMapper;

    @KafkaListener(
        topics = "key_chain_task",
        groupId = "ruoyi-chain-consumer-group",
        concurrency = "4",
        properties = {
            "max.poll.records=5",
            "max.poll.interval.ms=600000",
        }
    )
    public void onMessage(List<ConsumerRecord<String, String>> records) {
        for (ConsumerRecord<String, String> record : records) {
            try {
                if (!StringUtils.hasText(record.value())) continue;

                // 1. 解析消息
                ChainSyncEvent event = JSON.parseObject(record.value(), ChainSyncEvent.class);
                if (event == null) continue;

                String action = event.getActionType();
                List<Keymanage> keys = event.getKeys();

                if (keys == null || keys.isEmpty()) continue;

                // 2. 路由分发
                switch (action) {
                    case ChainSyncEvent.TYPE_ENROLL:
                        handleEnroll(keys);
                        break;
                    case ChainSyncEvent.TYPE_ROTATE:
                        handleRotate(keys);
                        break;
                    case ChainSyncEvent.TYPE_REVOKE:
                        handleStatusChange(keys, 3);
                        break;
                    case ChainSyncEvent.TYPE_FREEZE:
                        handleStatusChange(keys, 1);
                        break;
                    default:
                        log.warn("忽略未知的上链操作类型: {}", action);
                }
            } catch (Exception e) {
                log.error("消息处理异常，Offset: {}", record.offset(), e);
            }
        }
    }

    private void handleEnroll(List<Keymanage> keys) {
        for (Keymanage km : keys) {
            try {
                String finalPA = calculatePA(km);
                if (finalPA == null) {
                    log.error("KeyId: {} 公钥计算失败", km.getKeyId());
                    updateKeyStatus(km.getKeyId(), "2", null, null);
                    continue;
                }

                // 执行上链
                TransactionReceipt receipt = fiscoService.uploadKey(
                    km.getKeyId(), km.getUserName(), finalPA, "SM2", "ENCRYPT", false, km.getVersion()
                );

                // 处理结果
                handleTransactionReceipt(km.getKeyId(), receipt, "1");

            } catch (Exception e) {
                log.error("新增上链异常 KeyId: " + km.getKeyId(), e);
                updateKeyStatus(km.getKeyId(), "2", null, null);
            }
        }
    }

    private void handleRotate(List<Keymanage> keys) {
        for (Keymanage km : keys) {
            try {
                String finalPA = calculatePA(km);
                if (finalPA == null) continue;

                TransactionReceipt receipt = fiscoService.rotateKey(
                    km.getKeyId(), finalPA, km.getVersion()
                );

                handleTransactionReceipt(km.getKeyId(), receipt, "1");

            } catch (Exception e) {
                log.error("密钥轮换异常 KeyId: " + km.getKeyId(), e);
                updateKeyStatus(km.getKeyId(), "2", null, null);
            }
        }
    }

    private void handleStatusChange(List<Keymanage> keys, int targetStatus) {
        for (Keymanage km : keys) {
            try {
                TransactionReceipt receipt = fiscoService.changeKeyStatus(km.getKeyId(), targetStatus);
                // 状态变更仅记录 Hash，视业务需求决定是否更新 chainStatus
                handleTransactionReceipt(km.getKeyId(), receipt, null);
            } catch (Exception e) {
                log.error("状态更新异常 KeyId: " + km.getKeyId(), e);
            }
        }
    }

    /**
     * 核心：统一处理交易回执
     */
    private void handleTransactionReceipt(Long keyId, TransactionReceipt receipt, String successStatus) {
        if (receipt == null) {
            updateKeyStatus(keyId, "2", null, null);
            return;
        }

        // 检查状态码 (0x0 为成功)
        if (!receipt.isStatusOK()) {
            log.error("KeyId: {} 上链失败，状态码: {}, 信息: {}", keyId, receipt.getStatus(), receipt.getMessage());
            updateKeyStatus(keyId, "2", null, null);
            return;
        }

        // 获取 Hash 和 块高
        String txHash = receipt.getTransactionHash();
        Long blockHeight = parseBlockHeight(receipt.getBlockNumber());

        // 更新数据库
        updateKeyStatus(keyId, successStatus, txHash, blockHeight);
    }

    private Long parseBlockHeight(String blockNumberStr) {
        if (!StringUtils.hasText(blockNumberStr)) return 0L;
        try {
            if (blockNumberStr.startsWith("0x") || blockNumberStr.startsWith("0X")) {
                return new BigInteger(blockNumberStr.substring(2), 16).longValue();
            }
            return Long.valueOf(blockNumberStr);
        } catch (Exception e) {
            return 0L;
        }
    }

    private void updateKeyStatus(Long keyId, String chainStatus, String hash, Long height) {
        Keymanage updateKey = new Keymanage();
        updateKey.setKeyId(keyId);
        if (chainStatus != null) updateKey.setChainStatus(chainStatus);
        if (hash != null) updateKey.setChainHash(hash);
        if (height != null) updateKey.setBlockHeight(height);

        keymanageMapper.updatekeymanage(updateKey);
    }

    /**
     * 计算最终公钥 PA
     * 支持 SM2 和 SSCL 两种算法
     */
    private String calculatePA(Keymanage km) {
        try {
            if (km.getKeyValue() == null) return null;
            JSONObject kv = JSON.parseObject(km.getKeyValue());

            // ========== SSCL 算法分支 ==========
            String ssclKey = kv.getString("SSCLKey");
            if (ssclKey != null) {
                return calculateSSCLPublicKey(km, ssclKey);
            }

            // ========== SM2 算法分支 ==========
            String wA = kv.getString("finalPublicKey");
            if (wA == null) wA = kv.getString("publicKey"); // 兼容逻辑

            if (wA == null) return null;
            return sm2Service.calculateFinalPublicKey(km.getUserName(), wA);
        } catch (Exception e) {
            log.error("计算 PA 异常", e);
            return null;
        }
    }

    /**
     * SSCL 公钥计算
     * 公式: PA = uA + (eA * m) * G
     * 
     * @param km       密钥管理对象 (包含 uA)
     * @param ssclKey  SSCL 密钥值 (格式: 04 + m(64字符) + M(64字符))
     * @return 最终公钥 (04开头的 Hex 字符串)
     */
    private String calculateSSCLPublicKey(Keymanage km, String ssclKey) {
        try {
            // 1. 验证格式
            if (ssclKey == null || ssclKey.length() != 130 || !ssclKey.startsWith("04")) {
                log.error("SSCLKey 格式无效: {}", ssclKey);
                return null;
            }

            // 2. 提取 m (前 32 字节, 即第 3-66 位字符)
            String mHex = ssclKey.substring(2, 66);
            BigInteger m = new BigInteger(mHex, 16);

            // 3. 获取系统参数
            BigInteger eA = ssclGen.getEA();
            BigInteger n = ssclGen.getN();
            ECPoint G = ssclGen.getG();

            // 4. 解析用户部分公钥 uA
            String uAStr = km.getuA();
            if (uAStr == null || uAStr.length() != 130 || !uAStr.startsWith("04")) {
                log.error("用户部分公钥 uA 格式无效: {}", uAStr);
                return null;
            }
            String uxHex = uAStr.substring(2, 66);
            String uyHex = uAStr.substring(66, 130);
            BigInteger ux = new BigInteger(uxHex, 16);
            BigInteger uy = new BigInteger(uyHex, 16);
            ECPoint uA = ssclGen.getEcSpec().getCurve().createPoint(ux, uy);

            // 5. 计算 PA = uA + (eA * m mod n) * G
            BigInteger scalar = eA.multiply(m).mod(n);
            ECPoint part2 = G.multiply(scalar).normalize();
            ECPoint PA = uA.add(part2).normalize();

            // 6. 返回 04 开头的 Hex 字符串 (与 SM2 格式统一)
            return Hex.toHexString(PA.getEncoded(false)).toUpperCase();

        } catch (Exception e) {
            log.error("SSCL 公钥计算异常", e);
            return null;
        }
    }
}