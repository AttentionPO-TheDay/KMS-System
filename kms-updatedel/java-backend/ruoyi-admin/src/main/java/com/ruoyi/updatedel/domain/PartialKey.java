package com.ruoyi.updatedel.domain;

import java.math.BigInteger;
import lombok.Data;
import org.bouncycastle.math.ec.ECPoint;

@Data
public class PartialKey {
    private BigInteger tA;
    private ECPoint wA;
    private BigInteger mx;
    private BigInteger my;
}
