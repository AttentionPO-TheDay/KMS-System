package com.ruoyi.keymanage.domain;

import org.bouncycastle.math.ec.ECPoint;

import java.math.BigInteger;

/**
 * 部分私钥类
 */
public class PartialKey {

    /** SM2无证书部分私钥 */
    private BigInteger tA;
    /** SM2无证书声明公钥 */
    private ECPoint wA;

    /** SSCL无证书x坐标m */
    private BigInteger mx;
    /** SSCL无证书y坐标M */
    private BigInteger my;

    public BigInteger getMx() {
        return mx;
    }

    public void setMx(BigInteger mx) {
        this.mx = mx;
    }

    public BigInteger getMy() {
        return my;
    }

    public void setMy(BigInteger my) {
        this.my = my;
    }

    public BigInteger getTA() {
        return tA;}
    public ECPoint getWA() {
        return wA;
    }

    public void setTA(BigInteger tA) {
        this.tA = tA;
    }
    public void setWA(ECPoint wA) {
        this.wA = wA;
    }
}
