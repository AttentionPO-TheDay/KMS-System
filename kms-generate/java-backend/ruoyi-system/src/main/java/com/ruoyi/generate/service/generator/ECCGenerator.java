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
public class ECCGenerator implements ECConstants {
    private static final String NAME_ID = "sm2p256v1";
    private static final String MS_HEX = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";
    private static final SecureRandom RANDOM = new SecureRandom();

    static {
        Security.addProvider(new BouncyCastleProvider());
    }

    private final ECNamedCurveParameterSpec ecSpec = ECNamedCurveTable.getParameterSpec(NAME_ID);
    private final ECPoint g = ecSpec.getG();
    private final BigInteger n = ecSpec.getN();
    private final BigInteger a = ecSpec.getCurve().getA().toBigInteger();
    private final BigInteger b = ecSpec.getCurve().getB().toBigInteger();
    private final BigInteger ms = new BigInteger(MS_HEX, 16);
    private final ECPoint pPub = g.multiply(ms).normalize();
    private final SM3Digest hash256 = new SM3Digest();

    public PartialKey genPartialKey(UserIdentity userIdentity, String uA) {
        if (uA == null || uA.length() != 130 || !uA.startsWith("04")) {
            throw new IllegalArgumentException("公钥格式非法");
        }

        BigInteger x = new BigInteger(uA.substring(2, 66), 16);
        BigInteger y = new BigInteger(uA.substring(66, 130), 16);
        ECPoint uAPoint = ecSpec.getCurve().createPoint(x, y);
        if (!uAPoint.isValid()) {
            throw new IllegalArgumentException("用户公钥不在曲线上");
        }

        byte[] merged = concatBytes(
                convertBytes(getENTL(userIdentity.getIdentityData())),
                convertBytes(userIdentity.getIdentityData()),
                convertBytes(a, 32),
                convertBytes(b, 32),
                convertBytes(g.getAffineXCoord().toBigInteger(), 32),
                convertBytes(g.getAffineYCoord().toBigInteger(), 32),
                convertBytes(pPub.getAffineXCoord().toBigInteger(), 32),
                convertBytes(pPub.getAffineYCoord().toBigInteger(), 32)
        );
        hash256.update(merged, 0, merged.length);
        byte[] hA = new byte[hash256.getDigestSize()];
        hash256.doFinal(hA, 0);

        BigInteger w = randomNum();
        ECPoint wA = g.multiply(w).add(uAPoint).normalize();

        byte[] merged2 = concatBytes(
                convertBytes(wA.getAffineXCoord().toBigInteger(), 32),
                convertBytes(wA.getAffineYCoord().toBigInteger(), 32),
                hA
        );
        hash256.update(merged2, 0, merged2.length);
        byte[] lambdaBytes = new byte[hash256.getDigestSize()];
        hash256.doFinal(lambdaBytes, 0);
        BigInteger lambda = new BigInteger(1, lambdaBytes).mod(n);

        PartialKey partialKey = new PartialKey();
        partialKey.setTA(w.add(lambda.multiply(ms)).mod(n));
        partialKey.setWA(wA);
        return partialKey;
    }

    public ComParam getComParam() {
        ComParam comParam = new ComParam();
        comParam.setN(n);
        comParam.setG(g);
        comParam.setPPub(pPub);
        return comParam;
    }

    private short getENTL(String idA) {
        return (short) (idA.getBytes(StandardCharsets.UTF_8).length * 8);
    }

    private BigInteger randomNum() {
        int bitLength = n.bitLength();
        int minWeight = bitLength >>> 2;
        BigInteger value;
        do {
            do {
                value = BigIntegers.createRandomBigInteger(bitLength, RANDOM);
            } while (value.compareTo(ONE) < 0 || value.compareTo(n) >= 0);
        } while (WNafUtil.getNafWeight(value) < minWeight);
        return value;
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

    private byte[] convertBytes(short value) {
        return new byte[]{(byte) (value >> 8), (byte) value};
    }

    private byte[] convertBytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
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
