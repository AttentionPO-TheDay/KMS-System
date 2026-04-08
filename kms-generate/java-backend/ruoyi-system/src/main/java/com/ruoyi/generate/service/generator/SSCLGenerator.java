package com.ruoyi.generate.service.generator;

import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.PartialKey;
import com.ruoyi.generate.domain.UserIdentity;
import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.ECNamedCurveParameterSpec;
import org.bouncycastle.math.ec.ECConstants;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.math.ec.WNafUtil;
import org.bouncycastle.util.BigIntegers;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.Security;

@Component
public class SSCLGenerator implements ECConstants {
    private static final String NAME_ID = "sm2p256v1";
    private static final String MS_HEX = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";
    private static final int T = 10;

    static {
        Security.addProvider(new BouncyCastleProvider());
    }

    private final ECNamedCurveParameterSpec ecSpec = ECNamedCurveTable.getParameterSpec(NAME_ID);
    private final ECPoint g = ecSpec.getG();
    private final BigInteger n = ecSpec.getN();
    private final BigInteger ms = new BigInteger(MS_HEX, 16);
    private final ECPoint pPub = g.multiply(ms).normalize();
    private final BigInteger[] xIndexs = new BigInteger[T];
    private final BigInteger[] yIndexs = new BigInteger[T];
    private final BigInteger[] coefficients = new BigInteger[T + 1];
    private final SM3Digest hash256 = new SM3Digest();
    private final SecureRandom random = new SecureRandom();

    public SSCLGenerator() {
        coefficients[0] = ms.multiply(randomNum()).mod(n);
        for (int i = 1; i < T + 1; i++) {
            coefficients[i] = randomNum();
        }
        for (int i = 0; i < T; i++) {
            xIndexs[i] = randomNum();
            yIndexs[i] = computeShare(coefficients, xIndexs[i]);
        }
    }

    public PartialKey genPartialKey(UserIdentity userIdentity, String uA) {
        if (uA == null || uA.length() != 130 || !uA.startsWith("04")) {
            throw new IllegalArgumentException("公钥格式非法");
        }

        BigInteger ux = new BigInteger(uA.substring(2, 66), 16);
        BigInteger uy = new BigInteger(uA.substring(66, 130), 16);
        ECPoint uAPoint = ecSpec.getCurve().createPoint(ux, uy);
        if (!uAPoint.isValid()) {
            throw new IllegalArgumentException("用户公钥不在曲线上");
        }

        byte[] merged = concatBytes(convertBytes(ux, 32), convertBytes(uy, 32), userIdentity.getIdentityData().getBytes(StandardCharsets.UTF_8));
        hash256.update(merged, 0, merged.length);
        byte[] hA = new byte[hash256.getDigestSize()];
        hash256.doFinal(hA, 0);

        PartialKey partialKey = new PartialKey();
        partialKey.setMx(new BigInteger(1, hA).mod(n));
        partialKey.setMy(computeShare(coefficients, partialKey.getMx()));
        return partialKey;
    }

    public ComParam getComParam() {
        ComParam comParam = new ComParam();
        comParam.setN(n);
        comParam.setG(g);
        comParam.setPPub(pPub);
        comParam.setxIndex(xIndexs);
        comParam.setyIndex(yIndexs);
        return comParam;
    }

    public BigInteger getEA() {
        return coefficients[0];
    }

    private BigInteger randomNum() {
        int bitLength = n.bitLength();
        int minWeight = bitLength >>> 2;
        BigInteger value;
        do {
            do {
                value = BigIntegers.createRandomBigInteger(bitLength, random);
            } while (value.compareTo(ONE) < 0 || value.compareTo(n) >= 0);
        } while (WNafUtil.getNafWeight(value) < minWeight);
        return value;
    }

    private BigInteger computeShare(BigInteger[] factors, BigInteger xIndex) {
        BigInteger temp = BigInteger.ONE;
        BigInteger result = BigInteger.ZERO;
        for (BigInteger factor : factors) {
            result = result.add(factor.multiply(temp)).mod(n);
            temp = temp.multiply(xIndex);
        }
        return result.mod(n);
    }

    private byte[] convertBytes(BigInteger value, int fixedLength) {
        byte[] bytes = value.toByteArray();
        if (bytes.length > fixedLength) {
            byte[] result = new byte[fixedLength];
            System.arraycopy(bytes, bytes.length - fixedLength, result, 0, fixedLength);
            return result;
        }
        if (bytes.length < fixedLength) {
            byte[] result = new byte[fixedLength];
            System.arraycopy(bytes, 0, result, fixedLength - bytes.length, bytes.length);
            return result;
        }
        return bytes;
    }

    private byte[] concatBytes(byte[]... arrays) {
        try (ByteArrayOutputStream outputStream = new ByteArrayOutputStream()) {
            for (byte[] array : arrays) {
                if (array != null && array.length > 0) {
                    outputStream.write(array);
                }
            }
            return outputStream.toByteArray();
        } catch (IOException e) {
            throw new IllegalStateException("字节拼接失败", e);
        }
    }
}
