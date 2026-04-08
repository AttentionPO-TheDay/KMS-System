package com.ruoyi.generate.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.Map;

public class ComParam {
    private ECPoint G;
    private ECPoint PPub;
    private BigInteger n;
    private BigInteger[] xIndex;
    private BigInteger[] yIndex;

    public ECPoint getG() {
        return G;
    }

    public void setG(ECPoint g) {
        G = g;
    }

    public ECPoint getPPub() {
        return PPub;
    }

    public void setPPub(ECPoint PPub) {
        this.PPub = PPub;
    }

    public BigInteger getN() {
        return n;
    }

    public void setN(BigInteger n) {
        this.n = n;
    }

    public BigInteger[] getxIndex() {
        return xIndex;
    }

    public void setxIndex(BigInteger[] xIndex) {
        this.xIndex = xIndex;
    }

    public BigInteger[] getyIndex() {
        return yIndex;
    }

    public void setyIndex(BigInteger[] yIndex) {
        this.yIndex = yIndex;
    }

    public Map<String, Object> toMap() {
        Map<String, Object> pointMap = new HashMap<>();
        pointMap.put("G", encodePoint(G));
        pointMap.put("PPub", encodePoint(PPub));
        pointMap.put("N", toFixedLengthHex(n, 32));
        if (xIndex != null && yIndex != null && xIndex.length > 0 && yIndex.length > 0) {
            pointMap.put("xIndex", toHexArrayJson(xIndex));
            pointMap.put("yIndex", toHexArrayJson(yIndex));
        }
        return pointMap;
    }

    private String toHexArrayJson(BigInteger[] values) {
        String[] result = new String[values.length];
        for (int i = 0; i < values.length; i++) {
            result[i] = toFixedLengthHex(values[i], 32);
        }
        try {
            return new ObjectMapper().writeValueAsString(result);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("公共参数序列化失败", e);
        }
    }

    private String encodePoint(ECPoint point) {
        if (point == null) {
            return null;
        }
        return Hex.toHexString(point.getEncoded(false));
    }

    private static String toFixedLengthHex(BigInteger value, int byteLength) {
        byte[] bytes = BigIntegers.asUnsignedByteArray(byteLength, value);
        return Hex.toHexString(bytes);
    }
}
