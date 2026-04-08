package com.ruoyi.keymanage.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import org.bouncycastle.math.ec.ECPoint;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;

import java.util.HashMap;
import java.math.BigInteger;
import java.util.Map;

/**
 * ECC公共参数类
 */
public class ComParam {
    private ECPoint G; //G
    private ECPoint PPub; //系统主公钥
    private BigInteger n; //G的阶数

    //秘密共享设置下的公开x和y
    private BigInteger[] xIndex;
    private BigInteger[] yIndex;

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

    public ECPoint getG() {
        return G;
    }

    public void setG(ECPoint G) {
        this.G = G;
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

    public String toJsonG() throws JsonProcessingException {
        ObjectMapper objectMapper = new ObjectMapper();
        byte[] xBytes = G.getAffineXCoord().getEncoded();
        byte[] yBytes = G.getAffineYCoord().getEncoded();
        String xHex = bytesToHex(xBytes);
        String yHex = bytesToHex(yBytes);
        String GHex = "04" + xHex + yHex;
        byte[] ppubxBytes = PPub.getAffineXCoord().getEncoded();
        byte[] ppubyBytes = PPub.getAffineYCoord().getEncoded();
        String ppubxHex = bytesToHex(ppubxBytes);
        String ppubyHex = bytesToHex(ppubyBytes);
        String ppubstr = "04" + ppubxHex + ppubyHex;
        String nstr = toFixedLengthHex(n,32);;
        Map<String, String> pointMap = new HashMap<>();
        pointMap.put("G", GHex);
        pointMap.put("PPub", ppubstr);
        pointMap.put("N", nstr);

        boolean xValid = (xIndex != null && xIndex.length > 0);
        boolean yValid = (yIndex != null && yIndex.length > 0);
        if (xValid && yValid){
            String[] xArray = new String[xIndex.length];
            for (int i = 0; i < xIndex.length; i++) {
                xArray[i] = toFixedLengthHex(xIndex[i], 32);
            }
            String[] yArray = new String[yIndex.length];
            for (int i = 0; i < yIndex.length; i++) {
                yArray[i] = toFixedLengthHex(yIndex[i], 32);
            }
            pointMap.put("xIndex", objectMapper.writeValueAsString(xArray));
            pointMap.put("yIndex", objectMapper.writeValueAsString(yArray));
        }
        String json = objectMapper.writeValueAsString(pointMap);
        return json;
    }

    protected static String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }
    private static String toFixedLengthHex(BigInteger value, int byteLength) {
        byte[] bytes = BigIntegers.asUnsignedByteArray(byteLength, value);
        return Hex.toHexString(bytes);
    }
}
