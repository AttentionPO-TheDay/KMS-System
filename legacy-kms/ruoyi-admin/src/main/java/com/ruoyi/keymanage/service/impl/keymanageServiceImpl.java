package com.ruoyi.keymanage.service.impl;

import java.math.BigInteger;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.ruoyi.keymanage.domain.*;
import com.ruoyi.keymanage.service.impl.generator.ECCGenerator;
import com.ruoyi.keymanage.service.impl.generator.SSCLGenerator;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import com.ruoyi.keymanage.mapper.KeymanageMapper;
import com.ruoyi.keymanage.domain.Keymanage;
import com.ruoyi.keymanage.service.IKeymanageService;
import org.springframework.web.bind.annotation.RequestBody;

import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/**
 * 密钥管理Service业务层处理
 * @author ruoyi
 * @date 2025-01-14
 */
@Service
public class keymanageServiceImpl implements IKeymanageService
{
    @Autowired
    private KeymanageMapper keymanageMapper;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    private ECCGenerator eccGen = new ECCGenerator();

    @Autowired
    private SSCLGenerator ssclGen;

    /**
     * 查询密钥管理
     *
     * @param keyId 密钥管理主键
     * @return 密钥管理
     */
    @Override
    public Keymanage selectkeymanageByKeyId(Long keyId)
    {
        return keymanageMapper.selectkeymanageByKeyId(keyId);
    }

    /**
     * 查询密钥管理列表
     *
     * @param keymanage 密钥管理
     * @return 密钥管理
     */
    @Override
    public List<Keymanage> selectkeymanageList(Keymanage keymanage)
    {
        return keymanageMapper.selectkeymanageList(keymanage);
    }

    /**
     * 获取公共参数
     *
     * @return 公共参数
     */
    public String getComParam(Keymanage keymanage) throws JsonProcessingException
    {
        if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SM2".equals(keymanage.getEncrytName())) {
            return eccGen.getComParam().toJsonG();
        } else if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SSCL".equals(keymanage.getEncrytName())) {
            return ssclGen.getComParam().toJsonG();
        }
        return null;
    }

    /**
     * 新增密钥管理
     * 新增密钥管理
     *
     * @param keymanage 密钥管理
     * @return 结果
     */
    @Override
    public int insertkeymanage(Keymanage keymanage)
    {
        LocalDateTime now = LocalDateTime.now();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        String timestamp = now.format(formatter);

        keymanage.setCreTime(timestamp);
        keymanage.setUpdTime(timestamp);
        keymanage.setVersion(1); // 初始版本 v1
        keymanage.setStatus(KeyStatus.ACTIVE.getCode()); // 状态正常 ("0")
        keymanage.setChainStatus("0"); // 待上链

        // 生成密钥逻辑
        generateKeyLogic(keymanage);

        // 入库
        int rows = keymanageMapper.insertkeymanage(keymanage);

        // 发送上链任务 (新增使用 ENROLL)
        if (rows > 0 && keymanage.getKeyId() != null) {
            sendChainTask(ChainSyncEvent.TYPE_ENROLL, keymanage);
        }

        return rows;
    }

    /**
     * 修改密钥管理 (前端手动点击修改，通常意味着密钥轮换)
     */
    @Override
    public int updatekeymanage(Keymanage keymanage)
    {
        LocalDateTime now = LocalDateTime.now();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        String timestamp = now.format(formatter);
        keymanage.setUpdTime(timestamp);

        // 1. 获取旧数据以处理版本号
        Keymanage oldKey = keymanageMapper.selectkeymanageByKeyId(keymanage.getKeyId());
        if (oldKey != null) {
            // 版本号 +1
            keymanage.setVersion(oldKey.getVersion() != null ? oldKey.getVersion() + 1 : 2);
            // 补全生成密钥需要的关键信息(防止前端传参不全)
            if (keymanage.getuA() == null) keymanage.setuA(oldKey.getuA());
            if (keymanage.getKeyDomain() == null) keymanage.setKeyDomain(oldKey.getKeyDomain());
        } else {
            keymanage.setVersion(1);
        }

        // 2. 状态重置为 Active (即使之前是 Frozen 或其他状态，轮换后通常视为新的 Active 密钥)
        keymanage.setStatus(KeyStatus.ACTIVE.getCode());
        keymanage.setChainStatus("0");

        // 3. 重新生成密钥值
        generateKeyLogic(keymanage);

        // 4. 更新数据库
        int rows = keymanageMapper.updatekeymanage(keymanage);

        // 5. 发送上链任务
        if (rows > 0) {
            // 更新操作使用 ROTATE
            sendChainTask(ChainSyncEvent.TYPE_ROTATE, keymanage);
        }

        return rows;
    }

    /**
     * 新增：根据ID轮换密钥 (供 KafkaConsumer 调用)
     * 逻辑：查旧数据 -> 重新生成 -> 存库 -> 上链
     */
    @Override
    public void rotateKeyById(Long keyId) {
        // 1. 查旧数据
        Keymanage keymanage = keymanageMapper.selectkeymanageByKeyId(keyId);
        if (keymanage == null) {
            System.err.println("KeyId " + keyId + " 不存在，无法轮换");
            return;
        }

        // 2. 修改元数据 (直接在原对象上修改)
        // 版本号 +1
        keymanage.setVersion(keymanage.getVersion() != null ? keymanage.getVersion() + 1 : 2);

        // 状态重置
        String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        keymanage.setUpdTime(now);
        keymanage.setStatus(KeyStatus.ACTIVE.getCode()); // 重置为正常
        keymanage.setChainStatus("0"); // 重置为待上链

        // 3. 重新生成密钥
        generateKeyLogic(keymanage);

        // 4. 更新数据库
        int rows = keymanageMapper.updatekeymanage(keymanage);

        // 5. 发送上链任务 (ROTATE)
        if (rows > 0) {
            sendChainTask(ChainSyncEvent.TYPE_ROTATE, keymanage);
        }
    }

    /**
     * 批量删除密钥管理 (逻辑删除)
     * 修改逻辑：不再物理删除，而是将状态更新为 REVOKED ("3")
     */
    @Override
    public int deletekeymanageByKeyIds(Long[] keyIds)
    {
        // 1. 先发送回收通知 (区块链上记录 REVOKE 事件)
        List<Keymanage> revokeList = new ArrayList<>();
        for (Long id : keyIds) {
            Keymanage k = new Keymanage();
            k.setKeyId(id);
            revokeList.add(k);
        }

        if (!revokeList.isEmpty()) {
            ChainSyncEvent event = new ChainSyncEvent(ChainSyncEvent.TYPE_REVOKE, revokeList);
            try {
                kafkaTemplate.send("key_chain_task", JSON.toJSONString(event));
            } catch (Exception e) {
                e.printStackTrace();
            }
        }

        // 2. 更新数据库状态为已回收 (逻辑删除)
        int rows = 0;
        String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));

        for (Long id : keyIds) {
            Keymanage updateKey = new Keymanage();
            updateKey.setKeyId(id);
            // ✅ 使用枚举 REVOKED ("3")
            updateKey.setStatus(KeyStatus.REVOKED.getCode());
            updateKey.setUpdTime(now);

            // 调用 update 接口而非 delete 接口
            rows += keymanageMapper.updatekeymanage(updateKey);
        }

        return rows;
    }

    /**
     * 删除密钥管理信息
     */
    @Override
    public int deletekeymanageByKeyId(Long keyId)
    {
        return deletekeymanageByKeyIds(new Long[]{keyId});
    }

    @Override
    public int insertKeymanageBatch(List<Keymanage> list) {
        if (list == null || list.isEmpty()) return 0;
        return keymanageMapper.insertKeymanageBatch(list);
    }

    // =========================================================
    // 私有辅助方法
    // =========================================================

    private void sendChainTask(String actionType, Keymanage keymanage) {
        try {
            List<Keymanage> list = new ArrayList<>();
            list.add(keymanage);

            ChainSyncEvent event = new ChainSyncEvent(actionType, list);
            kafkaTemplate.send("key_chain_task", JSON.toJSONString(event));

            System.out.println("已发送上链任务: " + actionType + " ID=" + keymanage.getKeyId());
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    /**
     * 核心密钥生成逻辑
     */
    private void generateKeyLogic(Keymanage keymanage) {
        if ("对称加密".equals(keymanage.getEncrytType()) && "AES".equals(keymanage.getEncrytName())){
            try {
                // 获取AES密钥生成器实例
                KeyGenerator keyGen = KeyGenerator.getInstance("AES");
                keyGen.init(256);
                SecretKey secretKey = keyGen.generateKey();
                byte[] keyBytes = secretKey.getEncoded();
                keymanage.setKeyValue(bytesToHex(keyBytes));
            } catch (NoSuchAlgorithmException e) {
                e.printStackTrace();
            }
        } else if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SM2".equals(keymanage.getEncrytName())) {
            UserIdentity userIdentity = new UserIdentity();
            userIdentity.setIdentityData(keymanage.getUserName());
            keymanage.setUserIdentity(userIdentity);
            String uA = keymanage.getuA();

            PartialKey partialKey = eccGen.genPartialKey(userIdentity,uA);

            BigInteger tA = partialKey.getTA();
            BigInteger wAx = partialKey.getWA().getAffineXCoord().toBigInteger();
            BigInteger wAy = partialKey.getWA().getAffineYCoord().toBigInteger();
            String tAstr = toFixedLengthHex(tA,32);
            String wAxstr = toFixedLengthHex(wAx,32);
            String wAystr = toFixedLengthHex(wAy,32);
            String publicKey = "04" + wAxstr + wAystr;
            JSONObject jsonObject = new JSONObject();
            jsonObject.put("partialKey", tAstr);
            jsonObject.put("finalPublicKey", publicKey);
            if (partialKey.getKgcRandomW() != null) jsonObject.put("kgcRandomW", partialKey.getKgcRandomW().toString(16));
            if (partialKey.getKgcLambda() != null) jsonObject.put("kgcLambda", partialKey.getKgcLambda().toString(16));
            keymanage.setKeyValue(jsonObject.toJSONString());

        } else if ("无证书非对称加密".equals(keymanage.getEncrytType()) && "SSCL".equals(keymanage.getEncrytName())) {
            UserIdentity userIdentity = new UserIdentity();
            userIdentity.setIdentityData(keymanage.getUserName());
            keymanage.setUserIdentity(userIdentity);
            String uA = keymanage.getuA();

            PartialKey partialKey = ssclGen.genPartialKey(userIdentity,uA);

            BigInteger m = partialKey.getMx();
            BigInteger M = partialKey.getMy();
            String mstr = toFixedLengthHex(m,32);
            String Mstr = toFixedLengthHex(M,32);
            String SSCLKey = "04" + mstr + Mstr;
            JSONObject jsonObject = new JSONObject();
            jsonObject.put("SSCLKey", SSCLKey);
            jsonObject.put("kgcMx", mstr);
            jsonObject.put("SSCLDomian", keymanage.getKeyDomain());
            keymanage.setKeyValue(jsonObject.toJSONString());
        }
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private static String toFixedLengthHex(BigInteger value, int byteLength) {
        byte[] bytes = BigIntegers.asUnsignedByteArray(byteLength, value);
        return Hex.toHexString(bytes);
    }
}
