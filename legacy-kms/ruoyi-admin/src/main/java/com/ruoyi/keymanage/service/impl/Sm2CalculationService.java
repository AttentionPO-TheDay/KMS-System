package com.ruoyi.keymanage.service.impl;


import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve;
import org.bouncycastle.util.encoders.Hex;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.math.BigInteger;
import java.util.Arrays;

/**
 * SM2 无证书公钥计算服务
 * 负责将 Go 传来的部分公钥 (WA) 转换为最终公钥 (PA)
 */
@Service
public class Sm2CalculationService {

    // SM2 曲线定义
    private final SM2P256V1Curve curve = new SM2P256V1Curve();
    private final BigInteger n = curve.getOrder(); // 阶
    // SM2 基点 G
    private final ECPoint G = curve.createPoint(
            new BigInteger("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7", 16),
            new BigInteger("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0", 16)
    );

    // --- ⚠️ 必须与 Go 端完全一致的主密钥 ---
    private final String msHex = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";

    // 缓存：系统公钥 PPub 和 静态Hash后缀
    private ECPoint PPub;
    private byte[] staticHashSuffix;

    @PostConstruct
    public void init() {
        // 1. 计算 PPub = [ms]G
        BigInteger ms = new BigInteger(msHex, 16);
        this.PPub = G.multiply(ms).normalize();

        // 2. 预计算静态参数后缀 (与 Go 端的 suffixBuf 逻辑对应)
        // 顺序: a || b || Gx || Gy || PPubX || PPubY
        byte[] a = to32Bytes(curve.getA().toBigInteger());
        byte[] b = to32Bytes(curve.getB().toBigInteger());
        byte[] gx = to32Bytes(G.getAffineXCoord().toBigInteger());
        byte[] gy = to32Bytes(G.getAffineYCoord().toBigInteger());
        byte[] pPubX = to32Bytes(PPub.getAffineXCoord().toBigInteger());
        byte[] pPubY = to32Bytes(PPub.getAffineYCoord().toBigInteger());

        int len = 32 * 6;
        this.staticHashSuffix = new byte[len];
        System.arraycopy(a, 0, staticHashSuffix, 0, 32);
        System.arraycopy(b, 0, staticHashSuffix, 32, 32);
        System.arraycopy(gx, 0, staticHashSuffix, 64, 32);
        System.arraycopy(gy, 0, staticHashSuffix, 96, 32);
        System.arraycopy(pPubX, 0, staticHashSuffix, 128, 32);
        System.arraycopy(pPubY, 0, staticHashSuffix, 160, 32);
    }

    /**
     * 计算最终公钥 PA
     * @param userId 用户名 (ID_A)
     * @param uAStr Go 传来的 WA (Hex String, 04开头)
     * @return 最终公钥 PA (Hex String, 04开头)
     */
    public String calculateFinalPublicKey(String userId, String uAStr) {
        try {
            // 1. 解析 WA (部分公钥)
            if (uAStr.startsWith("04")) {
                uAStr = uAStr.substring(2);
            }
            byte[] uABytes = Hex.decode(uAStr);
            byte[] xBytes = Arrays.copyOfRange(uABytes, 0, 32);
            byte[] yBytes = Arrays.copyOfRange(uABytes, 32, 64);
            ECPoint WA = curve.createPoint(new BigInteger(1, xBytes), new BigInteger(1, yBytes));

            // 2. 计算 HA (与 Go 逻辑对应)
            // HA = SM3(ENTL || ID || ... || PPubY)
            SM3Digest digest = new SM3Digest();

            // ENTL
            int entlen = userId.getBytes().length * 8; // 注意：这里取 byte 长度
            digest.update((byte) (entlen >> 8));
            digest.update((byte) entlen);

            // ID
            byte[] idBytes = userId.getBytes();
            digest.update(idBytes, 0, idBytes.length);

            // Suffix
            digest.update(staticHashSuffix, 0, staticHashSuffix.length);

            byte[] HA = new byte[32];
            digest.doFinal(HA, 0);

            // 3. 计算 lambda
            // lambda = SM3(WA_x || WA_y || HA)
            digest.reset();
            byte[] waX = to32Bytes(WA.getAffineXCoord().toBigInteger());
            byte[] waY = to32Bytes(WA.getAffineYCoord().toBigInteger());

            digest.update(waX, 0, 32);
            digest.update(waY, 0, 32);
            digest.update(HA, 0, 32);

            byte[] lambdaBytes = new byte[32];
            digest.doFinal(lambdaBytes, 0);

            BigInteger lambda = new BigInteger(1, lambdaBytes).mod(n);

            // 4. 计算 PA = WA + [lambda]PPub
            ECPoint temp = PPub.multiply(lambda);
            ECPoint PA = WA.add(temp).normalize();

            // 5. 返回 Hex
            return Hex.toHexString(PA.getEncoded(false)).toUpperCase();

        } catch (Exception e) {
            e.printStackTrace();
            return null;
        }
    }

    // 辅助：转固定32字节
    private byte[] to32Bytes(BigInteger n) {
        byte[] b = n.toByteArray();
        if (b.length == 32) return b;
        byte[] res = new byte[32];
        if (b.length > 32) System.arraycopy(b, b.length - 32, res, 0, 32);
        else System.arraycopy(b, 0, res, 32 - b.length, b.length);
        return res;
    }
}
