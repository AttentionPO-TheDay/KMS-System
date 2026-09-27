package com.ruoyi.common.crypto;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * KGC（密钥生成中心）主私钥 ms 的**版本化**来源。
 *
 * <h2>为什么需要版本号</h2>
 * {@code ms} 是 PPub / SSCL 域份额 / 链上公钥 {@code P_A = W_A + λ·ms·G} 的共同种子。
 * 它一旦轮换，用旧 {@code ms} 算出的历史 {@code P_A} 就**再也复算不出来**，
 * 链上存证随之失去可验证性 —— 这正是本类原先注释里那句
 * "变更会使链上已存证公钥与库内数据不一致、历史存证无法校验"。
 *
 * <p>把 {@code ms} 做成带版本号的密钥集就解决了这个矛盾：
 * <ul>
 *   <li>{@code KGC_MASTER_SECRET} / {@code KGC_MASTER_SECRET_ID} —— 当前**启用**的密钥；</li>
 *   <li>{@code KGC_MASTER_SECRET_RETIRED} —— 已退役但**仍需保留**的密钥（JSON 映射）；</li>
 *   <li>每条密钥记录写明自己由哪个版本签发（{@code keymanage.ms_key_id}），
 *       复算历史 {@code P_A} 时按记录里的版本去取密钥。</li>
 * </ul>
 * 于是轮换只影响"新记录用哪把密钥"，不再破坏历史。
 *
 * <h2>为什么不许静默回退</h2>
 * 本类一度是"未配置就用公开的演示默认值，只打一条 WARN"。实测后果是：部署方的
 * {@code KGC_MASTER_SECRET} 一直是空的，于是**线上生效的就是那个公开值**；
 * 而且它还能经一个只读接口间接反推出来。现在未配置、为空、仍是演示值、格式非法
 * —— 一律抛异常让服务起不来。宁可起不来，也不要带着公开秘密对外服务。
 *
 * <h2>退役密钥的使用边界</h2>
 * 退役密钥**只用于历史复算**（{@link #getById(String)}），
 * 绝不会被 {@link #getActive()} 返回，因此不可能被用来签发新记录。
 */
@Component
public final class KgcMasterSecret {

    private static final Logger log = LoggerFactory.getLogger(KgcMasterSecret.class);

    /**
     * 历史遗留的公开演示主私钥。
     *
     * <p><b>它已不可用于签发新记录</b>：把它配成启用密钥会直接启动失败。
     * 但它现在是 <b>ms_v1</b> —— 早期那批密钥（含 10 条已上链记录）确实是它签发的，
     * 所以它必须留在 {@code KGC_MASTER_SECRET_RETIRED} 里，否则那些历史 {@code P_A}
     * 就永久失去可复算性。
     */
    public static final String LEGACY_DEMO_SECRET =
        "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9";

    /** 演示值的版本号。历史记录默认归属它。 */
    public static final String LEGACY_DEMO_ID = "ms_v1";

    /** 未显式配置版本号时的缺省启用版本。 */
    public static final String DEFAULT_ACTIVE_ID = "ms_v2";

    private static final int HEX_LENGTH = 64;

    private static volatile Map<String, String> secrets = Collections.emptyMap();
    private static volatile String activeId = DEFAULT_ACTIVE_ID;

    private KgcMasterSecret() {
    }

    /** Spring 注入入口：固定不变量的密钥集。 */
    @Value("${kms.kgc.master-secrets-json:}")
    public void configureSecrets(String unused) {
        // 实际取值一律走环境变量，避免把密钥写进 application.yml。
        // 保留这个注入点只是为了与既有配置结构兼容。
        synchronized (KgcMasterSecret.class) {
            secrets = Collections.emptyMap();
            activeId = DEFAULT_ACTIVE_ID;
        }
        reload();
    }

    /** 当前启用密钥的版本号。 */
    public static String activeId() {
        ensureLoaded();
        return activeId;
    }

    /**
     * 取**当前启用**的密钥。签发新记录一律用它。
     *
     * <p>不会返回退役密钥，因此不存在"新记录被旧密钥签发"的可能。
     */
    public static String getActive() {
        ensureLoaded();
        String value = secrets.get(activeId);
        if (value == null) {
            throw new IllegalStateException(
                "KGC 主私钥配置不一致：当前启用版本 " + activeId + " 在密钥集中不存在。"
                    + "请检查 KGC_MASTER_SECRET / KGC_MASTER_SECRET_ID。");
        }
        return value;
    }

    /**
     * 按版本号取密钥，**包含退役密钥**。用于复算历史 {@code P_A}。
     *
     * @param keyId 记录里的 {@code ms_key_id}；为空时按 {@link #LEGACY_DEMO_ID} 处理
     *              （早期记录没有这个字段，它们都是 ms_v1 签发的）
     */
    public static String getById(String keyId) {
        ensureLoaded();
        String id = (keyId == null || keyId.trim().isEmpty()) ? LEGACY_DEMO_ID : keyId.trim();
        String value = secrets.get(id);
        if (value == null) {
            throw new IllegalStateException(
                "找不到版本为 " + id + " 的 KGC 主私钥，无法复算该记录的公钥 P_A。"
                    + "若该版本确实用过，请把它补进 KGC_MASTER_SECRET_RETIRED；"
                    + "**不要**删掉退役密钥，那会让对应的历史记录永久失去可验证性。");
        }
        return value;
    }

    /** 该版本是否已退役（仅用于展示与排查）。 */
    public static boolean isRetired(String keyId) {
        String id = (keyId == null || keyId.trim().isEmpty()) ? LEGACY_DEMO_ID : keyId.trim();
        return !id.equals(activeId());
    }

    /** 当前启用版本是否仍是公开的演示值。正常运行时恒为 false（否则服务已启动失败）。 */
    public static boolean isUsingDemoDefault() {
        try {
            return LEGACY_DEMO_SECRET.equalsIgnoreCase(getActive());
        } catch (RuntimeException ex) {
            return false;
        }
    }

    /**
     * 兼容旧调用点：等价于 {@link #getActive()}。
     *
     * @deprecated 新代码请明确写 {@code getActive()}（签发）或 {@code getById(id)}（复算），
     *             以免日后分不清该用哪一个。
     */
    @Deprecated
    public static String get() {
        return getActive();
    }

    // -----------------------------------------------------------------------
    // 加载与校验
    // -----------------------------------------------------------------------

    private static void ensureLoaded() {
        if (!secrets.isEmpty()) {
            return;
        }
        synchronized (KgcMasterSecret.class) {
            if (!secrets.isEmpty()) {
                return;
            }
            reload();
        }
    }

    private static void reload() {
        Map<String, String> loaded = new LinkedHashMap<>();

        // 先装退役密钥：它们允许（且应该）包含那个公开的历史值
        String retiredJson = System.getenv("KGC_MASTER_SECRET_RETIRED");
        if (retiredJson != null && !retiredJson.trim().isEmpty()) {
            try {
                JSONObject retired = JSON.parseObject(retiredJson.trim());
                for (String id : retired.keySet()) {
                    String secret = retired.getString(id);
                    if (secret == null || secret.trim().isEmpty()) {
                        continue;
                    }
                    loaded.put(id.trim(), validateHex(secret.trim(), "退役密钥 " + id));
                }
            } catch (RuntimeException ex) {
                throw new IllegalStateException(
                    "KGC_MASTER_SECRET_RETIRED 解析失败（应为 JSON 映射 {\"ms_v1\":\"<64 位十六进制>\"}）："
                        + ex.getMessage(), ex);
            }
        }

        // 再装启用密钥
        String configuredId = trimToNull(System.getenv("KGC_MASTER_SECRET_ID"));
        String id = configuredId == null ? DEFAULT_ACTIVE_ID : configuredId;
        String active = trimToNull(System.getenv("KGC_MASTER_SECRET"));
        if (active == null) {
            throw new IllegalStateException(
                "未配置 KGC 主私钥（环境变量 KGC_MASTER_SECRET）。该值是无证书方案里唯一的秘密，"
                    + "缺失时不能再回退到公开的演示值 —— 那等于把秘密公开。"
                    + "请注入一把真实随机值后重启，生成示例：openssl rand -hex 32。"
                    + "参见 kms-ops/.env.example。");
        }
        active = validateHex(active, "启用密钥 " + id);
        if (LEGACY_DEMO_SECRET.equalsIgnoreCase(active)) {
            throw new IllegalStateException(
                "KGC 主私钥的**启用版本**仍是公开的演示默认值（" + LEGACY_DEMO_SECRET + "）。"
                    + "该值存在于源码与历史文档中，且可被只读接口间接反推，"
                    + "任何拿到它的人都能为任意身份伪造部分私钥。"
                    + "请轮换为真实随机值（openssl rand -hex 32）后重启。"
                    + "注意：这个旧值应当移到 KGC_MASTER_SECRET_RETIRED 里保留"
                    + "（作为 " + LEGACY_DEMO_ID + "），以便历史记录仍可复算。");
        }
        loaded.put(id, active);

        secrets = Collections.unmodifiableMap(loaded);
        activeId = id;
        log.info("KGC 主私钥已加载：启用版本={}，密钥集共 {} 个版本（含 {} 个退役版本）",
            id, loaded.size(), loaded.size() - 1);
    }

    private static String validateHex(String value, String label) {
        if (value.length() != HEX_LENGTH || !value.matches("[0-9A-Fa-f]{" + HEX_LENGTH + "}")) {
            throw new IllegalStateException(
                "KGC 主私钥格式非法（" + label + "）：应为 64 位十六进制（32 字节），"
                    + "实际长度为 " + value.length() + "。生成示例：openssl rand -hex 32。");
        }
        return value.toUpperCase();
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}