package com.ruoyi.updatedel.service.generator;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.PartialKey;
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
public class SsclKeyGenerator implements ECConstants {
    private static final String NAME_ID = "sm2p256v1";
    private static final String MS_HEX = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";
    private static final int T = 10;
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    static {
        Security.addProvider(new BouncyCastleProvider());
    }

    private final ECNamedCurveParameterSpec ecSpec = ECNamedCurveTable.getParameterSpec(NAME_ID);
    private final ECPoint g = ecSpec.getG();
    private final BigInteger n = ecSpec.getN();
    private final BigInteger ms = new BigInteger(MS_HEX, 16);
    private final BigInteger[] coefficients = initCoefficients();

    public String generate(String userName, String ua, String keyDomain) {
        PartialKey partialKey = genPartialKey(userName, ua);
        Map<String, String> payload = new LinkedHashMap<>();
        payload.put("SSCLKey", "04" + toFixedLengthHex(partialKey.getMx(), 32) + toFixedLengthHex(partialKey.getMy(), 32));
        payload.put("SSCLDomian", keyDomain == null ? "A" : keyDomain);
        try {
            return OBJECT_MAPPER.writeValueAsString(payload);
        } catch (IOException ex) {
            throw new IllegalStateException("SSCL 密钥序列化失败", ex);
        }
    }

    private PartialKey genPartialKey(String userName, String ua) {
        ECPoint uAPoint = parsePoint(ua);
        byte[] conBytes1 = concatBytes(
            convertBytes(uAPoint.getAffineXCoord().toBigInteger(), 32),
            convertBytes(uAPoint.getAffineYCoord().toBigInteger(), 32),
            userName.getBytes(StandardCharsets.UTF_8));

        SM3Digest digest = new SM3Digest();
        digest.update(conBytes1, 0, conBytes1.length);
        byte[] hA = new byte[digest.getDigestSize()];
        digest.doFinal(hA, 0);

        PartialKey partialKey = new PartialKey();
        BigInteger m = new BigInteger(1, hA).mod(n);
        partialKey.setMx(m);
        partialKey.setMy(computeShare(coefficients, m));
        return partialKey;
    }

    private BigInteger[] initCoefficients() {
        BigInteger[] values = new BigInteger[T + 1];
        BigInteger wA = randomNum();
        values[0] = ms.multiply(wA).mod(n);
        for (int i = 1; i < values.length; i++) {
            values[i] = randomNum();
        }
        return values;
    }

    private BigInteger computeShare(BigInteger[] values, BigInteger xIndex) {
        BigInteger temp = BigInteger.ONE;
        BigInteger result = BigInteger.ZERO;
        for (BigInteger value : values) {
            result = result.add(value.multiply(temp)).mod(n);
            temp = temp.multiply(xIndex).mod(n);
        }
        return result.mod(n);
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

    private ECPoint parsePoint(String value) {
        if (value == null || value.length() != 130 || !value.startsWith("04")) {
            throw new IllegalArgumentException("SSCL 用户部分公钥格式非法");
        }
        BigInteger x = new BigInteger(value.substring(2, 66), 16);
        BigInteger y = new BigInteger(value.substring(66), 16);
        ECPoint point = ecSpec.getCurve().createPoint(x, y);
        if (!point.isValid()) {
            throw new IllegalArgumentException("SSCL 用户部分公钥不在曲线上");
        }
        return point;
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
        } catch (IOException ex) {
            throw new IllegalStateException("SSCL 拼接字节失败", ex);
        }
    }

    private String toFixedLengthHex(BigInteger value, int byteLength) {
        return Hex.toHexString(BigIntegers.asUnsignedByteArray(byteLength, value));
    }
}
