package com.ruoyi.generate.service.generator;

import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.PartialKey;
import com.ruoyi.generate.domain.UserIdentity;
import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.ECNamedCurveParameterSpec;
import org.bouncycastle.math.ec.ECConstants;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.BigIntegers;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.Security;

@Component
public class SSCLGenerator implements ECConstants {
    private static final String NAME_ID = "sm2p256v1";
    private static final int T = 10;

    // ---------------------------------------------------------------------
    // SSCL 域参数：由 ms 确定性派生，**不得使用随机源**（重要）
    // ---------------------------------------------------------------------
    // 本类是全仓库**第三份** SSCL 实现（另两份：Go 的
    // `kms-generate/go-backend/service/generator/sscl_generator.go`，与 Java 的
    // `kms-updatedel/.../service/generator/SsclKeyGenerator.java`）。
    //
    // 原来三份各自 `new SecureRandom()` 独立随机出多项式，由此产生两个问题：
    //   1. **不抗重启**：每次进程启动都换一组参数，而 /comparam 发布的正是这些参数，
    //      于是启动前生成的密钥与启动后的公开参数对不上，客户端插值必然失败；
    //   2. **跨实现不一致**：/comparam 由 Go 提供，本类却用自己的多项式算 my，
    //      两边的点不共线 —— 插值出来的常量项是垃圾，密钥直接不可用。
    //
    // 现在三份实现都用同一套派生规则（标准 SM3，种子 = ms）：
    //     derive(label):
    //         for counter in 0x00..0xFF:
    //             candidate = BigInteger(1, SM3(msBytes(32B 大端) || utf8(label) || 单字节 counter))
    //             if 1 <= candidate < n: return candidate
    //     wa      = derive("KMS-SSCL-DOMAIN-v1|wa")
    //     coef[0] = ms*wa mod n            ← **不哈希**，保持 SSCLEA 的既有关系
    //     coef[i] = derive("KMS-SSCL-DOMAIN-v1|coef|" + i)     i = 1..T（十进制，不补零）
    //     x[i]    = 取第一个满足条件的 attempt（i 从 1 开始）：
    //                 derive("KMS-SSCL-DOMAIN-v1|x|" + i + "|" + attempt)
    //               要求 != 0 且不与已接受的 x 重复（首次不冲突者胜出）
    //
    // ⚠️ label 必须与 Go 侧**逐字节一致**（UTF-8、无长度前缀、无终止符）。
    //    改这里就必须同步改 Go 的 `sscl_domain_derive.go`；Go 侧有一个
    //    `TestSSCLDomainKnownAnswer` 把这些数值钉死了，改错会在那边变成红测。
    private static final String DOMAIN_LABEL_PREFIX = "KMS-SSCL-DOMAIN-v1|";
    private static final int SM3_DIGEST_SIZE = 32;

    static {
        Security.addProvider(new BouncyCastleProvider());
    }

    private final ECNamedCurveParameterSpec ecSpec = ECNamedCurveTable.getParameterSpec(NAME_ID);
    private final ECPoint g = ecSpec.getG();
    private final BigInteger n = ecSpec.getN();
    // 主私钥来自统一配置源；缺失或仍是演示值会让服务直接起不来（见 KgcMasterSecret 说明）。
    // 签发路径：必须用**当前启用**版本的 ms（getActive 不会返回退役密钥）。
    // 生成出来的记录会带上 ms_key_id，日后按它复算 P_A。
    private final BigInteger ms = new BigInteger(KgcMasterSecret.getActive(), 16);
    private final ECPoint pPub = g.multiply(ms).normalize();
    private final BigInteger[] xIndexs = new BigInteger[T];
    private final BigInteger[] yIndexs = new BigInteger[T];
    private final BigInteger[] coefficients = new BigInteger[T + 1];
    private final SM3Digest hash256 = new SM3Digest();

    public SSCLGenerator() {
        coefficients[0] = ms.multiply(deriveDomainScalar(DOMAIN_LABEL_PREFIX + "wa")).mod(n);
        for (int i = 1; i < T + 1; i++) {
            coefficients[i] = deriveDomainScalar(DOMAIN_LABEL_PREFIX + "coef|" + i);
        }
        for (int i = 0; i < T; i++) {
            // Go 侧 i 是 1-based（x[1]..x[10]），这里转成同样的编号
            xIndexs[i] = deriveDomainXIndex(i + 1, xIndexs, i);
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

    /**
     * 用 SM3 从主私钥 ms 确定性地派生一个 [1, n) 范围内的标量。
     *
     * <p>同一把 ms + 同一个 label，在任何机器、任何时刻、任何进程里都必须得到同一个值 ——
     * 这正是"重启后公开参数漂移"与"三份实现各有一条多项式"两个症状的共同解药。
     *
     * <p>若 256 次计数全部落在 [1, n) 之外（概率约 2^-256，实际不可能）则抛异常：
     * 静默返回错误值会把不可用的公开参数发出去，比直接失败危险得多。
     */
    private BigInteger deriveDomainScalar(String label) {
        byte[] msBytes = BigIntegers.asUnsignedByteArray(32, ms);
        byte[] labelBytes = label.getBytes(StandardCharsets.UTF_8);
        byte[] counter = new byte[1];
        for (int c = 0; c <= 0xFF; c++) {
            counter[0] = (byte) c;
            SM3Digest digest = new SM3Digest();
            digest.update(msBytes, 0, msBytes.length);
            digest.update(labelBytes, 0, labelBytes.length);
            digest.update(counter, 0, counter.length);
            byte[] out = new byte[SM3_DIGEST_SIZE];
            digest.doFinal(out, 0);
            BigInteger candidate = new BigInteger(1, out);
            if (candidate.compareTo(BigInteger.ONE) >= 0 && candidate.compareTo(n) < 0) {
                return candidate;
            }
        }
        throw new IllegalStateException(
            "SSCL 域参数派生失败：SM3 计数器 0x00..0xFF 全部被拒（label=" + label + "）");
    }

    /**
     * 派生第 {@code index}（1-based，与 Go 侧一致）个求值点 x。
     *
     * <p>插值要求所有 x 两两不同（客户端要算 {@code xi - xj} 的模逆），
     * 因此用"首次不冲突者胜出"的规则：attempt 从 0 递增，
     * 取第一个非零且未出现过的候选。冲突概率约 2^-256，
     * 但规则必须钉死，否则 Go 与 Java 在极端情况下会分叉。
     */
    private BigInteger deriveDomainXIndex(int index, BigInteger[] accepted, int acceptedCount) {
        for (int attempt = 0; attempt <= 0xFF; attempt++) {
            BigInteger candidate = deriveDomainScalar(
                DOMAIN_LABEL_PREFIX + "x|" + index + "|" + attempt);
            if (candidate.signum() == 0) {
                continue;
            }
            boolean duplicated = false;
            for (int i = 0; i < acceptedCount; i++) {
                if (candidate.equals(accepted[i])) {
                    duplicated = true;
                    break;
                }
            }
            if (!duplicated) {
                return candidate;
            }
        }
        throw new IllegalStateException(
            "SSCL 求值点派生失败：x|" + index + " 的 0x00..0xFF 次尝试全部冲突");
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
