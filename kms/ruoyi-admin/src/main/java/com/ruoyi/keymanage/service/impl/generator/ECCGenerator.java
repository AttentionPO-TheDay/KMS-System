package com.ruoyi.keymanage.service.impl.generator;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.math.BigInteger;
import java.security.Security;
import java.io.ByteArrayOutputStream;
import java.io.IOException;

import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.ECNamedCurveParameterSpec;
import org.bouncycastle.math.ec.ECMultiplier;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.math.ec.FixedPointCombMultiplier;
import org.bouncycastle.math.ec.WNafUtil;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.math.ec.ECConstants;

import com.ruoyi.keymanage.service.IGenerator;
import com.ruoyi.keymanage.domain.ComParam;
import com.ruoyi.keymanage.domain.UserIdentity;
import com.ruoyi.keymanage.domain.PartialKey;
import org.bouncycastle.util.encoders.Hex;

/**
 * SM2无证书类
 * 包含SM2无证书机制的KGC端的主要实现
 */
public class ECCGenerator implements ECConstants, IGenerator {
    // 国标推荐曲线
    private static final String nameId = "sm2p256v1";
    private static final String msHex = "6BDD93B2 10F79415 FE0F6388 C1C932C2 08319FF7 D7E99C97 2B3535C9 F19A9FF9";
    // 随机数器
    private static final SecureRandom random = new SecureRandom();

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

    // 是否初始化
    private boolean isInitialized = false;


    // sm3杂凑算法
    static {
        Security.addProvider(new BouncyCastleProvider());
    }
    public SM3Digest hash256 = new SM3Digest();



    public ECCGenerator() {

        String msHexStr = msHex.replaceAll("\\s+","");
        ms = new BigInteger(msHexStr,16);
        PPub =  G.multiply(ms).normalize();

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
        BigInteger xPPub = PPub.getAffineXCoord().toBigInteger();
        BigInteger yPPub = PPub.getAffineYCoord().toBigInteger();
        // System.out.println("xyPPub:" + xPPub.toString(16) + " " + yPPub.toString(16));
        BigInteger xG = G.getAffineXCoord().toBigInteger();
        BigInteger yG = G.getAffineYCoord().toBigInteger();
        String idA = userIdentity.getIdentityData();
        short ENTLA = getENTL(idA);

        //将uA转化为点
        if (uA == null || uA.length() != 130) {
            throw new IllegalArgumentException("公钥必须为130字符");
        }
        if (!uA.startsWith("04")) {
            throw new IllegalArgumentException("仅支持未压缩公钥格式");
        }
        String px = uA.substring(2, 66);
        String py = uA.substring(66,130);
        BigInteger x = new BigInteger(px, 16);
        BigInteger y = new BigInteger(py, 16);
        ECPoint uAPoint = ecSpec.getCurve().createPoint(x, y);
        //System.out.println("uAPoint: " + uAPoint.isValid());
        if (!uAPoint.isValid()) {
            throw new IllegalArgumentException("用户所给uAPoint (x,y) is not on the curve");
        }

        //计算比特串
        byte[] xPPubBytes = convertBytes(xPPub,32);
        byte[] yPPubBytes = convertBytes(yPPub,32);
        byte[] xGBytes = convertBytes(xG,32);
        byte[] yGBytes = convertBytes(yG,32);
        byte[] aBytes = convertBytes(a,32);
        byte[] bBytes = convertBytes(b,32);
        byte[] idABytes = convertBytes(idA);
        byte[] ENTLABytes = convertBytes(ENTLA);
        //System.out.println("idA: " + idA);
        //System.out.println("ENTLA: " + ENTLABytes.length);

        byte[] conBytes1 = concatBytes(ENTLABytes,idABytes,aBytes,bBytes,xGBytes,yGBytes,xPPubBytes,yPPubBytes);
        //System.out.println("conBytes1:" + conBytes1.length);
        hash256.update(conBytes1, 0, conBytes1.length);
        byte[] hA = new byte[hash256.getDigestSize()];
        hash256.doFinal(hA, 0);
        //System.out.println("hA:" + hA.length);
        //System.out.println("hA:" + Hex.toHexString(hA));

//        //官方example
//        String exam = "abc";
//        byte[] examBytes = exam.getBytes();
//        hash256.update(examBytes, 0, examBytes.length);
//        byte[] exam1 = new byte[hash256.getDigestSize()];
//        hash256.doFinal(exam1, 0);
//        System.out.println("exam1:" + exam1.length);
//        System.out.println("exam1:" + Hex.toHexString(exam1));

        // 每次调用生成新的随机数 w，确保密钥轮换时能生成不同的 finalPublicKey
        BigInteger w = randomNum();
        // ECPoint wA = createBasePointMultiplier().multiply(G, w).normalize().add(uA);
        ECPoint wA = G.multiply(w).add(uAPoint).normalize();

        BigInteger xWA = wA.getAffineXCoord().toBigInteger();
        BigInteger yWA = wA.getAffineYCoord().toBigInteger();
        //System.out.println("xWA:"+xWA.toString(16));
        //System.out.println("yWA:"+yWA.toString(16));
        byte[] xWABytes = convertBytes(xWA,32);
        byte[] yWABytes = convertBytes(yWA,32);
        byte[] conBytes2 = concatBytes(xWABytes,yWABytes,hA);
        hash256.update(conBytes2, 0, conBytes2.length);
        byte[] lambdaBytes = new byte[hash256.getDigestSize()];
        hash256.doFinal(lambdaBytes, 0);

        BigInteger lambda = new BigInteger(lambdaBytes).mod(n);
        //System.out.println("lambda:"+lambda.toString(16));
        BigInteger tA = (w.add(lambda.multiply(ms))).mod(n);
        //System.out.println("tA:"+tA.toString(16));
        PartialKey partialKey = new PartialKey();
        partialKey.setTA(tA);
        partialKey.setWA(wA);

        return partialKey;
    }



    /**
     * 返回KGC椭圆曲线的主要参数
     * @return
     */
    @Override
    public ComParam getComParam() {
        if (isInitialized()) {
            ComParam comParam = new ComParam();
            comParam.setN(n);
            comParam.setG(G);
            comParam.setPPub(PPub);
            return comParam;
        } else {
            ComParam comParam = new ComParam();
            return comParam;
        }
    }

    @Override
    public int setComParam(ComParam comParam) {
        n = comParam.getN();
        G = comParam.getG();
        PPub = comParam.getPPub();
        return 1;
    }

    protected short getENTL(String idA) {
        byte[] bytes = idA.getBytes(StandardCharsets.UTF_8);
        return (short) (bytes.length * 8);
    }
    protected short getENTL(BigInteger idA) {
        return (short) (idA.bitLength());
    }
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
    protected byte[] convertBytes(int var1) {
        byte[] bytes = new byte[4];
        bytes[0] = (byte) (var1 >> 24);
        bytes[1] = (byte) (var1 >> 16);
        bytes[2] = (byte) (var1 >> 8);
        bytes[3] = (byte) var1;
        return bytes;
    }
    protected byte[] convertBytes(short var1) {
        byte[] bytes = new byte[2];
        bytes[0] = (byte) (var1 >> 8);
        bytes[1] = (byte) var1;
        return bytes;
    }
    protected byte[] convertBytes(String var1) {
        return var1.getBytes(StandardCharsets.UTF_8);
    }
    protected ECMultiplier createBasePointMultiplier() {
        return new FixedPointCombMultiplier();
    }
    protected boolean isOutOfRangeD(BigInteger var1, BigInteger var2) {
        return var1.compareTo(ONE) < 0 || var1.compareTo(var2) >= 0;
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
