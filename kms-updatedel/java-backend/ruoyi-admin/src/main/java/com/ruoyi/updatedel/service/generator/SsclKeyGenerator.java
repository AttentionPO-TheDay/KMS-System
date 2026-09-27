package com.ruoyi.updatedel.service.generator;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.updatedel.domain.PartialKey;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.Security;
import java.util.LinkedHashMap;
import java.util.Map;
import org.bouncycastle.crypto.digests.SM3Digest;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.ECNamedCurveParameterSpec;
import org.bouncycastle.math.ec.ECConstants;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.BigIntegers;
import org.bouncycastle.util.encoders.Hex;
import org.springframework.stereotype.Component;

/**
 * SSCL 部分私钥生成器（Java 侧）。
 *
 * <h2>SSCL 域参数必须由主私钥 ms 确定性派生（本次修复的核心）</h2>
 * SSCL 把一条 T 次多项式的份额当作"公开参数"发布，域秘密藏在常数项
 * {@code coefficients[0] = ms*wa mod n} 中，客户端在 x=0 处对 T+1 个点做拉格朗日插值
 * 还原它。这里原来是每次构造 Bean 都随机抽 {@code wa} 与 {@code coefficients[1..T]}，
 * 于是同一个部署会出现两套互不相同的多项式：
 * <ul>
 *   <li>{@code GET /comparam} 由 <b>Go</b> 服务的 {@code sscl_generator.go} 提供，
 *       发布的是 Go 的多项式 f 上的点 {@code (xIndexs[i], yIndexs[i])}；</li>
 *   <li>生命周期 update 路径的 SSCL 密钥材料由<b>本类</b>生成，
 *       {@code my = g(mx)} 落在 Java 自己的多项式 g 上。</li>
 * </ul>
 * T+1 个点不在同一条 T 次多项式上，客户端插值出来的常数项是垃圾 ——
 * 也就是说 update 路径此前产出的 SSCL 密钥<b>本来就不可用</b>；
 * 更早的那个"重启后参数漂移、存量密钥失配"只是它的同源弱化版本。
 *
 * <p>现在两侧都不再用随机数，而是用标准 SM3 从 ms 派生同一组域参数：
 * <pre>
 *   msBytes  = ms 的 32 字节大端表示
 *   counter  = 单字节大端，0x00 起，被拒则 +1
 *   derive(label):
 *       for counter in 0x00..0xFF:
 *           candidate = BigInteger(1, SM3(msBytes || utf8(label) || counter))
 *           if 1 &lt;= candidate &lt; n: return candidate
 *       raise error（实际不可能发生）
 *
 *   wa      = derive("KMS-SSCL-DOMAIN-v1|wa")
 *   coef[0] = (ms * wa) mod n                       &lt;-- 不是哈希出来的
 *   coef[i] = derive("KMS-SSCL-DOMAIN-v1|coef|" + i)   i = 1..T（十进制，不补零）
 * </pre>
 * {@code coef[0]} 必须留在 {@code ms*wa mod n} 上：既有关系 {@code SSCLEA = coef[0]} 与
 * 客户端的 {@code dA = 插值常数项 * m mod n} 依赖它，改成哈希值会废掉所有已签发密钥。
 * Java 侧不发布评测点，因此<b>不需要</b>派生 {@code x[i]}（那是 Go 独有的职责）。
 *
 * <h2>必须与 Go 保持逐字节镜像（改这里就必须改那边）</h2>
 * 本类与 Go 侧
 * {@code kms-generate/go-backend/service/generator/sscl_domain_derive.go}
 * （被 {@code sscl_generator.go} 的 {@code newSSCLGenerator} 使用）是同一条派生规则的
 * 两份镜像实现。标签字符串、UTF-8 编码、字节序、拒绝条件必须完全一致；
 * 只改一边会让客户端拿到的 T+1 个点重新落到两条不同的多项式上，插值立刻失效。
 * 修改后必须跑两边的一致性比对（见交付说明中的跨语言测试）。
 *
 * <h2>轮换 ms 的影响</h2>
 * 域参数完全由 ms 决定，轮换 {@code KGC_MASTER_SECRET} 会同时改变 wa、coef[1..T]、
 * coef[0]（进而 SSCLEA）以及 Go 侧发布的 xIndexs/yIndexs 与 PPub = ms*G。
 * 存量密钥必须整体重新登记，否则旧密钥的客户端私钥与新的公开参数不再匹配。
 * 详见 {@code doc/kms-restructure-plan.md} 的 R17。
 */
@Component
public class SsclKeyGenerator implements ECConstants {
    private static final String NAME_ID = "sm2p256v1";
    private static final int T = 10;
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /** 派生标签统一前缀（ASCII、区分大小写，与 Go 侧逐字节一致，不得改动）。 */
    private static final String DOMAIN_LABEL_PREFIX = "KMS-SSCL-DOMAIN-v1|";

    /** 标准 SM3 输出长度（字节）。 */
    private static final int SM3_DIGEST_SIZE = 32;

    static {
        Security.addProvider(new BouncyCastleProvider());
    }

    private final ECNamedCurveParameterSpec ecSpec = ECNamedCurveTable.getParameterSpec(NAME_ID);
    private final ECPoint g = ecSpec.getG();
    private final BigInteger n = ecSpec.getN();
    // 主私钥来自统一配置源，不再硬编码（默认值与历史一致，见 KgcMasterSecret 说明）。
    // 签发路径：必须用**当前启用**版本的 ms（getActive 不会返回退役密钥）。
    // 生成出来的记录会带上 ms_key_id，日后按它复算 P_A。
    private final BigInteger ms = new BigInteger(KgcMasterSecret.getActive(), 16);
    private final BigInteger[] coefficients = initCoefficients();

    public String generate(String userName, String ua, String keyDomain) {
        PartialKey partialKey = genPartialKey(userName, ua);
        Map<String, String> payload = new LinkedHashMap<>();
        payload.put("SSCLKey", "04" + toFixedLengthHex(partialKey.getMx(), 32) + toFixedLengthHex(partialKey.getMy(), 32));
        payload.put("SSCLEA", toFixedLengthHex(coefficients[0], 32));
        payload.put("SSCLDomain", keyDomain == null ? "A" : keyDomain);
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

    /**
     * 初始化 SSCL 多项式系数：全部由 ms 确定性派生，不再使用任何随机源。
     *
     * <p>与 Go 侧 {@code sscl_domain_derive.go} 的
     * {@code deriveDomainScalar} 必须逐字节等价 —— 否则 Go 发布的
     * {@code (xIndexs[i], yIndexs[i])} 与本类算出的 {@code my} 不共线，
     * 客户端插值必然失败。
     */
    private BigInteger[] initCoefficients() {
        BigInteger[] values = new BigInteger[T + 1];
        BigInteger wA = deriveDomainScalar(DOMAIN_LABEL_PREFIX + "wa");
        values[0] = ms.multiply(wA).mod(n);
        for (int i = 1; i < values.length; i++) {
            values[i] = deriveDomainScalar(DOMAIN_LABEL_PREFIX + "coef|" + i);
        }
        return values;
    }

    /**
     * 用 SM3 从主私钥 ms 确定性地派生一个 [1, n) 范围内的标量。
     *
     * <p>与随机抽样的区别：同一把 ms + 同一个 label 在任何机器、任何时刻、任何进程里
     * 都必须得到同一个值 —— 这正是"重启后 SSCL 公开参数漂移"与"Go/Java 两条多项式"
     * 两个症状的共同解药。
     *
     * <p>label 必须与 Go 侧逐字节一致（UTF-8、无长度前缀、无终止符）。
     * 若 256 次计数全部落在 [1, n) 之外（概率约 2^-256，实际不可能）则抛异常：
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

    private BigInteger computeShare(BigInteger[] values, BigInteger xIndex) {
        BigInteger temp = BigInteger.ONE;
        BigInteger result = BigInteger.ZERO;
        for (BigInteger value : values) {
            result = result.add(value.multiply(temp)).mod(n);
            temp = temp.multiply(xIndex).mod(n);
        }
        return result.mod(n);
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
