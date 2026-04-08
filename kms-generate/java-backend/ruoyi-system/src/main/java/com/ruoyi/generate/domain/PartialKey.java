package com.ruoyi.generate.domain;

import org.bouncycastle.math.ec.ECPoint;

import java.math.BigInteger;

public class PartialKey {
    private BigInteger tA;
    private ECPoint wA;
    private BigInteger mx;
    private BigInteger my;

    public BigInteger getTA() {
        return tA;
    }

    public void setTA(BigInteger tA) {
        this.tA = tA;
    }

    public ECPoint getWA() {
        return wA;
    }

    public void setWA(ECPoint wA) {
        this.wA = wA;
    }

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
}
