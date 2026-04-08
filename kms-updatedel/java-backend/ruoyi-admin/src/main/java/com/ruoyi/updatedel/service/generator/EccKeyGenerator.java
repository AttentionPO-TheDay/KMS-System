package com.ruoyi.updatedel.service.generator;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.PartialKey;
import com.ruoyi.updatedel.domain.UserIdentity;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.Security;
import java.util.LinkedHashMap;
import java.util.Map;
import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.ECNamedCurveParameterSpec;
import org.bouncycastle.math.ec.ECConstants;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.math.ec.WNafUtil;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;
import org.springframework.stereotype.Component;

@Component
public class EccKeyGenerator implements ECConstants {
    private static final String NAME_ID = "sm2p256v1";
    private static final String MS_HEX = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

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

    public String generate(String userName, String ua) {
        PartialKey partialKey = genPartialKey(userName, ua);
        Map<String, String> payload = new LinkedHashMap<>();
        payload.put("partialKey", toFixedLengthHex(partialKey.getTA(), 32));
        payload.put("finalPublicKey", "04" + toFixedLengthHex(partialKey.getWA().getAffineXCoord().toBigInteger(), 32)
            + toFixedLengthHex(partialKey.getWA().getAffineYCoord().toBigInteger(), 32));
        try {
            return OBJECT_MAPPER.writeValueAsString(payload);
        } catch (IOException ex) {
            throw new IllegalStateException("SM2 密钥序列化失败", ex);
        }
    }

    private PartialKey genPartialKey(String userName, String ua) {
        UserIdentity userIdentity = new UserIdentity();
        userIdentity.setIdentityData(userName);

        BigInteger xPPub = pPub.getAffineXCoord().toBigInteger();
        BigInteger yPPub = pPub.getAffineYCoord().toBigInteger();
        BigInteger xG = g.getAffineXCoord().toBigInteger();
        BigInteger yG = g.getAffineYCoord().toBigInteger();

        ECPoint uAPoint = parsePoint(ua);
        byte[] conBytes1 = concatBytes(
            convertBytes(getENTL(userName)),
            userName.getBytes(StandardCharsets.UTF_8),
            convertBytes(a, 32),
            convertBytes(b, 32),
            convertBytes(xG, 32),
            convertBytes(yG, 32),
            convertBytes(xPPub, 32),
            convertBytes(yPPub, 32));

        SM3Digest digest = new SM3Digest();
        digest.update(conBytes1, 0, conBytes1.length);
        byte[] hA = new byte[digest.getDigestSize()];
        digest.doFinal(hA, 0);

        BigInteger w = randomNum();
        ECPoint wA = g.multiply(w).add(uAPoint).normalize();

        byte[] conBytes2 = concatBytes(
            convertBytes(wA.getAffineXCoord().toBigInteger(), 32),
            convertBytes(wA.getAffineYCoord().toBigInteger(), 32),
            hA);
        digest.update(conBytes2, 0, conBytes2.length);
        byte[] lambdaBytes = new byte[digest.getDigestSize()];
        digest.doFinal(lambdaBytes, 0);

        BigInteger lambda = new BigInteger(1, lambdaBytes).mod(n);
        PartialKey partialKey = new PartialKey();
        partialKey.setTA(w.add(lambda.multiply(ms)).mod(n));
        partialKey.setWA(wA);
        return partialKey;
    }

    private ECPoint parsePoint(String value) {
        if (value == null || value.length() != 130 || !value.startsWith("04")) {
            throw new IllegalArgumentException("SM2 用户部分公钥格式非法");
        }
        BigInteger x = new BigInteger(value.substring(2, 66), 16);
        BigInteger y = new BigInteger(value.substring(66), 16);
        ECPoint point = ecSpec.getCurve().createPoint(x, y);
        if (!point.isValid()) {
            throw new IllegalArgumentException("SM2 用户部分公钥不在曲线上");
        }
        return point;
    }

    private short getENTL(String idA) {
        return (short) (idA.getBytes(StandardCharsets.UTF_8).length * 8);
    }

    private BigInteger randomNum() {
        int bitLength = n.bitLength();
        int minWeight = bitLength >>> 2;
        BigInteger candidate;
        do {
            do {
                candidate = BigIntegers.createRandomBigInteger(bitLength, RANDOM);
            } while (candidate.compareTo(ONE) < 0 || candidate.compareTo(n) >= 0);
        } while (WNafUtil.getNafWeight(candidate) < minWeight);
        return candidate;
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
        return new byte[] {(byte) (value >> 8), (byte) value};
    }

    private byte[] concatBytes(byte[]... arrays) {
        try (ByteArrayOutputStream outputStream = new ByteArrayOutputStream()) {
            for (byte[] array : arrays) {
                if (array != null && array.length > 0) {
                    outputStream.write(array);
                }
            }
            return outputStream.toByteArray();
        } catch (IOException ex) {
            throw new IllegalStateException("SM2 拼接字节失败", ex);
        }
    }

    private String toFixedLengthHex(BigInteger value, int byteLength) {
        return Hex.toHexString(BigIntegers.asUnsignedByteArray(byteLength, value));
    }
}
