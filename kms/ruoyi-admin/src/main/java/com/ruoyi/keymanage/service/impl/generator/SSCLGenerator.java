package com.ruoyi.keymanage.service.impl.generator;

import com.ruoyi.keymanage.domain.ComParam;
import com.ruoyi.keymanage.domain.PartialKey;
import com.ruoyi.keymanage.domain.UserIdentity;
import com.ruoyi.keymanage.service.IGenerator;
import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.ECNamedCurveParameterSpec;
import org.bouncycastle.math.ec.ECConstants;

import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.math.ec.WNafUtil;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.Security;

import org.springframework.stereotype.Component;

/**
 * SSCL 密钥生成器 (单例 Bean)
 * 基于秘密共享的无证书公钥密码算法
 */
@Component
public class SSCLGenerator implements ECConstants, IGenerator {
    // 选择椭圆曲线
    private static final String nameId = "sm2p256v1";
    private static final String msHex = "6BDD93B2 10F79415 FE0F6388 C1C932C2 08319FF7 D7E99C97 2B3535C9 F19A9FF9";
    private ECNamedCurveParameterSpec ecSpec = ECNamedCurveTable.getParameterSpec(nameId);
    // 公共参数
    private ECPoint G = ecSpec.getG();
    private BigInteger n = ecSpec.getN();
    private BigInteger a = ecSpec.getCurve().getA().toBigInteger();
    private BigInteger b = ecSpec.getCurve().getB().toBigInteger();

    // 主密钥
    private BigInteger ms;
    // 主公钥
    private ECPoint PPub;
    // 秘密共享的阈值t
    private static final int t = 10;
    // 秘密共享的点
    BigInteger[] xIndexs = new BigInteger[t];
    BigInteger[] yIndexs = new BigInteger[t];
    // 秘密共享的系数
    BigInteger[] coefficients = new BigInteger[t+1];

    // sm3杂凑算法
    static {
        Security.addProvider(new BouncyCastleProvider());
    }
    public SM3Digest hash256 = new SM3Digest();
    // 随机数器
    SecureRandom random = new SecureRandom();
    // 是否初始化
    private boolean isInitialized = false;

    public SSCLGenerator() {

        String msHexStr = msHex.replaceAll("\\s+","");
        ms = new BigInteger(msHexStr,16);
        PPub =  G.multiply(ms).normalize();
        BigInteger WA = randomNum();
        BigInteger eA = ms.multiply(WA).mod(n);
        coefficients[0] = eA;
        //System.out.println("共享多项式系数(设t=10)：");
        for (int i = 1; i < t+1; i++) {
            coefficients[i] = randomNum();
            //System.out.println(coefficients[i].toString(16));
        }
        for (int i = 0; i < t; i++) {
            xIndexs[i] = randomNum();
        }

        for (int i = 0; i < t; i++) {
            yIndexs[i] = computeShare(coefficients,xIndexs[i]);
        }

        isInitialized = true;
    }
    public boolean isInitialized() {
        return this.isInitialized;
    }

    /**
     * 输入用户的标识和部分公钥，返回部分私钥
     * @param userIdentity
     * @param uA
     * @return partialKey
     */
    @Override
    public PartialKey genPartialKey(UserIdentity userIdentity, String uA) {
        String idA = userIdentity.getIdentityData();
        byte[] idABytes = convertBytes(idA);

        //将uA转化为点,uA是部分公钥
        if (uA == null || uA.length() != 130) {
            throw new IllegalArgumentException("公钥必须为130字符");
        }
        if (!uA.startsWith("04")) {
            throw new IllegalArgumentException("仅支持未压缩公钥格式");
        }
        String px = uA.substring(2, 66);
        String py = uA.substring(66,130);
        BigInteger ux = new BigInteger(px, 16);
        BigInteger uy = new BigInteger(py, 16);
        ECPoint uAPoint = ecSpec.getCurve().createPoint(ux, uy);
        if (!uAPoint.isValid()) {
            throw new IllegalArgumentException("用户所给uAPoint (x,y) is not on the curve");
        }
        byte[] uxBytes = convertBytes(ux,32);
        byte[] uyBytes = convertBytes(uy,32);

        byte[] conBytes1 = concatBytes(uxBytes,uyBytes,idABytes);
        //System.out.println("conBytes1:" + conBytes1.length);
        hash256.update(conBytes1, 0, conBytes1.length);
        byte[] hA = new byte[hash256.getDigestSize()];
        hash256.doFinal(hA, 0);
        System.out.println("hA:" + hA.length);
        System.out.println("hA:" + Hex.toHexString(hA));

        BigInteger m = new BigInteger(1,hA).mod(n);
        BigInteger M = computeShare(coefficients,m);

        PartialKey partialKey = new PartialKey();
        partialKey.setMx(m);
        partialKey.setMy(M);
        return partialKey;
    }

    @Override
    public ComParam getComParam() {
        ComParam comParam = new ComParam();
        if (isInitialized()) {
            comParam.setN(n);
            comParam.setG(G);
            comParam.setPPub(PPub);
            comParam.setxIndex(xIndexs);
            comParam.setyIndex(yIndexs);
            return comParam;
        } else {
            return comParam;
        }
    }

    /**
     * 获取秘密系数 eA (coefficients[0])
     * 用于上链时计算最终公钥: PA = uA + (eA * m) * G
     */
    public BigInteger getEA() {
        return coefficients[0];
    }

    /**
     * 获取基点 G
     */
    public ECPoint getG() {
        return G;
    }

    /**
     * 获取阶 n
     */
    public BigInteger getN() {
        return n;
    }

    /**
     * 获取曲线参数 (用于解析点)
     */
    public ECNamedCurveParameterSpec getEcSpec() {
        return ecSpec;
    }

    @Override
    public int setComParam(ComParam comParam) {
        return 0;
    }

    /**
     * 生成0-n范围内的随机数
     * @return
     */
    protected BigInteger randomNum() {
        int var1 = n.bitLength();
        int var2 = var1 >>> 2;

        BigInteger var3;
        do {
            while(true) {
                var3 = BigIntegers.createRandomBigInteger(var1, random);
                if (isOutOfRangeD(var3, n)) {
                    continue;
                }
                break;
            }
        } while(WNafUtil.getNafWeight(var3) < var2);
        return var3;
    }
    protected boolean isOutOfRangeD(BigInteger var1, BigInteger var2) {
        return var1.compareTo(ONE) < 0 || var1.compareTo(var2) >= 0;
    }

    /**
     * 计算秘密共享
     */
    protected BigInteger computeShare(BigInteger[] coefficients, BigInteger xIndex) {
        int len = coefficients.length;
        BigInteger temp = BigInteger.ONE;
        BigInteger result = BigInteger.ZERO;
        for (int i = 0; i < len; i++) {
            BigInteger cur = coefficients[i].multiply(temp);
            temp = temp.multiply(xIndex);
            result = result.add(cur).mod(n);
        }
        return result.mod(n);
    }
    //字节串转换，左大右小，为大端序
    protected byte[] convertBytes(BigInteger var1, int fixedLength) {
        byte[] bytes =  var1.toByteArray();

        // 处理前导零或不足的情况
        if (bytes.length > fixedLength) {
            // 去除前导零
            byte[] result = new byte[fixedLength];
            System.arraycopy(bytes, bytes.length - fixedLength, result, 0, fixedLength);
            return result;
        } else if (bytes.length < fixedLength) {
            // 补前导零
            byte[] result = new byte[fixedLength];
            System.arraycopy(bytes, 0, result, fixedLength - bytes.length, bytes.length);
            return result;
        }
        return bytes;
    }
    protected byte[] convertBytes(String var1) {
        return var1.getBytes(StandardCharsets.UTF_8);
    }
    protected byte[] concatBytes(byte[]... arrays) {
        try (ByteArrayOutputStream outputStream = new ByteArrayOutputStream()) {
            for (byte[] array : arrays) {
                if (array != null && array.length > 0) {
                    outputStream.write(array);
                }
            }
            return outputStream.toByteArray();
        } catch (IOException e) {
            throw new RuntimeException("合并比特串失败", e);
            }
        }
}
