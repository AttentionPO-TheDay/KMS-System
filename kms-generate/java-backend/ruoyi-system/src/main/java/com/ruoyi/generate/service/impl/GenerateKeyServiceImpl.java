package com.ruoyi.generate.service.impl;

import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.domain.KeyStatus;
import com.ruoyi.generate.domain.PartialKey;
import com.ruoyi.generate.domain.UserIdentity;
import com.ruoyi.generate.mapper.KeymanageMapper;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.generator.ECCGenerator;
import com.ruoyi.generate.service.generator.SSCLGenerator;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.math.BigInteger;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 生成密钥服务实现
 */
@Service
public class GenerateKeyServiceImpl implements GenerateKeyService {

    private static final Logger log = LoggerFactory.getLogger(GenerateKeyServiceImpl.class);

    @Autowired
    private KeymanageMapper keymanageMapper;

    @Autowired
    private ECCGenerator eccGenerator;

    @Autowired
    private SSCLGenerator ssclGenerator;

    @Override
    public Keymanage selectKeyById(Long keyId) {
        return keymanageMapper.selectkeymanageByKeyId(keyId);
    }

    @Override
    public List<Keymanage> selectKeyList(Keymanage keymanage) {
        return keymanageMapper.selectkeymanageList(keymanage);
    }

    @Override
    public int insertKeyBatch(List<Keymanage> list) {
        if (list == null || list.isEmpty()) {
            return 0;
        }
        int rows = keymanageMapper.insertKeymanageBatch(list);
        log.info("批量插入密钥 {} 条", rows);
        return rows;
    }

    @Override
    public int insertKey(Keymanage keymanage) {
        String now = now();
        keymanage.setCreTime(now);
        keymanage.setUpdTime(now);
        keymanage.setVersion(1);
        keymanage.setStatus(KeyStatus.ACTIVE.getCode());
        keymanage.setChainStatus("0");
        if (isBlank(keymanage.getKeyValue())) {
            generateKeyValue(keymanage);
        }
        return keymanageMapper.insertkeymanage(keymanage);
    }

    @Override
    public int insertHistoryRecord(Keymanage keymanage) {
        String now = now();
        keymanage.setCreTime(isBlank(keymanage.getCreTime()) ? now : keymanage.getCreTime());
        keymanage.setUpdTime(isBlank(keymanage.getUpdTime()) ? keymanage.getCreTime() : keymanage.getUpdTime());
        keymanage.setVersion(keymanage.getVersion() == null || keymanage.getVersion() < 1 ? 1 : keymanage.getVersion());
        keymanage.setAutoUpdate(isBlank(keymanage.getAutoUpdate()) ? "0" : keymanage.getAutoUpdate());
        keymanage.setStatus(isBlank(keymanage.getStatus()) ? KeyStatus.ACTIVE.getCode() : keymanage.getStatus());
        keymanage.setChainStatus(isBlank(keymanage.getChainStatus()) ? "0" : keymanage.getChainStatus());
        keymanage.setKeyDomain(isBlank(keymanage.getKeyDomain()) ? "A" : keymanage.getKeyDomain().trim());
        return keymanageMapper.insertkeymanage(keymanage);
    }

    @Override
    public int updateKey(Keymanage keymanage) {
        Keymanage oldKey = keymanageMapper.selectkeymanageByKeyId(keymanage.getKeyId());
        if (oldKey == null) {
            return 0;
        }

        keymanage.setUpdTime(now());
        keymanage.setVersion(oldKey.getVersion() == null ? 1 : oldKey.getVersion() + 1);
        if (keymanage.getUserId() == null) {
            keymanage.setUserId(oldKey.getUserId());
        }
        if (isBlank(keymanage.getUserName())) {
            keymanage.setUserName(oldKey.getUserName());
        }
        if (isBlank(keymanage.getEncrytType())) {
            keymanage.setEncrytType(oldKey.getEncrytType());
        }
        if (isBlank(keymanage.getEncrytName())) {
            keymanage.setEncrytName(oldKey.getEncrytName());
        }
        if (isBlank(keymanage.getuA())) {
            keymanage.setuA(oldKey.getuA());
        }
        if (isBlank(keymanage.getKeyDomain())) {
            keymanage.setKeyDomain(oldKey.getKeyDomain());
        }
        if (isBlank(keymanage.getKeyName())) {
            keymanage.setKeyName(oldKey.getKeyName());
        }
        if (isBlank(keymanage.getKeyUse())) {
            keymanage.setKeyUse(oldKey.getKeyUse());
        }
        if (isBlank(keymanage.getDemoNodeId())) {
            keymanage.setDemoNodeId(oldKey.getDemoNodeId());
        }
        if (isBlank(keymanage.getDemoRecordId())) {
            keymanage.setDemoRecordId(oldKey.getDemoRecordId());
        }
        if (isBlank(keymanage.getDemoResultStatus())) {
            keymanage.setDemoResultStatus(oldKey.getDemoResultStatus());
        }
        keymanage.setStatus(KeyStatus.ACTIVE.getCode());
        keymanage.setChainStatus("0");
        if (isBlank(keymanage.getKeyValue())) {
            generateKeyValue(keymanage);
        }
        return keymanageMapper.updatekeymanage(keymanage);
    }

    @Override
    public int deleteKey(Long keyId) {
        return keymanageMapper.deletekeymanageByKeyId(keyId);
    }

    @Override
    public ComParam getComParam(String encrytType, String encrytName) {
        if ("无证书非对称加密".equals(encrytType)) {
            if ("SM2".equals(encrytName)) {
                return eccGenerator.getComParam();
            }
            if ("SSCL".equals(encrytName)) {
                return ssclGenerator.getComParam();
            }
        }
        return null;
    }

    @Override
    public int updateChainStatus(Long keyId, String chainStatus, String chainHash, Long blockHeight) {
        Keymanage updateKey = new Keymanage();
        updateKey.setKeyId(keyId);
        if (chainStatus != null) {
            updateKey.setChainStatus(chainStatus);
        }
        if (chainHash != null) {
            updateKey.setChainHash(chainHash);
        }
        if (blockHeight != null) {
            updateKey.setBlockHeight(blockHeight);
        }
        return keymanageMapper.updatekeymanage(updateKey);
    }

    private void generateKeyValue(Keymanage keymanage) {
        if (!"无证书非对称加密".equals(keymanage.getEncrytType())) {
            throw new IllegalArgumentException("仅支持无证书密钥生成");
        }

        UserIdentity userIdentity = new UserIdentity();
        userIdentity.setIdentityData(keymanage.getUserName());
        keymanage.setUserIdentity(userIdentity);

        if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SM2".equals(keymanage.getEncrytName())) {
            PartialKey partialKey = eccGenerator.genPartialKey(userIdentity, keymanage.getuA());
            String tA = toFixedLengthHex(partialKey.getTA(), 32);
            String wAx = toFixedLengthHex(partialKey.getWA().getAffineXCoord().toBigInteger(), 32);
            String wAy = toFixedLengthHex(partialKey.getWA().getAffineYCoord().toBigInteger(), 32);
            JSONObject jsonObject = new JSONObject();
            jsonObject.put("partialKey", tA);
            jsonObject.put("finalPublicKey", "04" + wAx + wAy);
            keymanage.setKeyValue(jsonObject.toJSONString());
            return;
        }

        if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SSCL".equals(keymanage.getEncrytName())) {
            PartialKey partialKey = ssclGenerator.genPartialKey(userIdentity, keymanage.getuA());
            JSONObject jsonObject = new JSONObject();
            jsonObject.put("SSCLKey", "04" + toFixedLengthHex(partialKey.getMx(), 32) + toFixedLengthHex(partialKey.getMy(), 32));
            jsonObject.put("SSCLEA", toFixedLengthHex(ssclGenerator.getEA(), 32));
            jsonObject.put("SSCLDomain", keymanage.getKeyDomain());
            keymanage.setKeyValue(jsonObject.toJSONString());
            return;
        }

        throw new IllegalArgumentException("仅支持 SM2 和 SSCL 算法");
    }

    private String now() {
        return LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private static String toFixedLengthHex(BigInteger value, int byteLength) {
        byte[] bytes = BigIntegers.asUnsignedByteArray(byteLength, value);
        return Hex.toHexString(bytes);
    }
}
