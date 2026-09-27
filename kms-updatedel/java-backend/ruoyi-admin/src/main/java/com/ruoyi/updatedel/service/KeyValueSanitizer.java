package com.ruoyi.updatedel.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.updatedel.domain.Keymanage;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * {@code keymanage.key_value} 的脱敏器。
 *
 * <h2>为什么需要它</h2>
 * {@code key_value} 是**密钥材料**，不是普通字段。实测它会被三类接口原样返回：
 * <ul>
 *   <li>{@code GET /generate/key/list}、{@code GET /generate/key/{keyId}}</li>
 *   <li>{@code GET /generate/keymanage/list}、{@code GET /generate/keymanage/{keyId}}</li>
 *   <li>{@code GET /lifecycle/keymanage/list}、{@code /{keyId}}、{@code /analysis/{keyId}}</li>
 * </ul>
 * 而它的内容按算法差别很大：
 * <ul>
 *   <li><b>SM2 / SSCL</b>：KGC 分片（{@code partialKey} / {@code SSCLKey}/{@code SSCLEA}）。
 *       属主拿到它 + 自己浏览器里的本地份额才能算出最终私钥，所以**属主需要**；
 *       但它对别人是敏感材料。</li>
 *   <li><b>CL-Kyber / CL-Falcon</b>：里面是**完整私钥**（{@code private_key}）。
 *       这类材料任何人都没有理由从接口读到。</li>
 * </ul>
 *
 * <h2>策略</h2>
 * <table>
 *   <tr><th>场景</th><th>行为</th></tr>
 *   <tr><td>列表接口</td><td><b>一律不带材料</b>（{@code keyValue = null}）。
 *       已核对全部现网页面：没有任何列表消费 {@code keyValue} 做展示或计算 ——
 *       需要材料的地方走的都是「创建/更新响应」或「详情接口」。</td></tr>
 *   <tr><td>详情接口 · 属主 · SM2/SSCL</td><td>原样返回（客户端要据此现算 d_A）</td></tr>
 *   <tr><td>详情接口 · 其他情况</td><td>降级为**公钥视图**，并显式标注已脱敏</td></tr>
 * </table>
 *
 * 降级后的 {@code keyValue} 是一个可解析的 JSON：
 * <pre>{"redacted":true,"reason":"material_not_returned","publicValue":"04..."}</pre>
 * 前端已有的 {@code safeJsonParse} + "缺少 partialKey" 分支能自然处理它，
 * 不需要为"字段变成 null"再写一套判空。
 *
 * <p>顺带一提：{@code userName} 之类字段不受影响；本类只动 {@code keyValue}。
 */
public final class KeyValueSanitizer {

    private static final Logger log = LoggerFactory.getLogger(KeyValueSanitizer.class);

    /** 属主本人可以拿到材料的算法。其余（含格算法）一律不返回。 */
    private static final Set<String> OWNER_MATERIAL_ALGORITHMS =
        new HashSet<>(Arrays.asList("SM2", "SSCL"));

    private static final String CERTIFICATELESS_TYPE = "无证书非对称加密";

    private KeyValueSanitizer() {
    }

    /** 列表：抹掉密钥材料。 */
    public static void stripMaterial(Keymanage keymanage) {
        if (keymanage != null) {
            keymanage.setKeyValue(null);
        }
    }

    /** 列表：抹掉密钥材料。 */
    public static void stripMaterial(List<Keymanage> list) {
        if (list == null) {
            return;
        }
        for (Keymanage item : list) {
            stripMaterial(item);
        }
    }

    /**
     * 详情：按「是否属主 + 算法」决定是否返回材料。
     *
     * @param keymanage 待处理的密钥（原地修改）
     * @param isOwner   调用方是否为该密钥的属主
     */
    public static void sanitizeDetail(Keymanage keymanage, boolean isOwner) {
        if (keymanage == null) {
            return;
        }
        String material = keymanage.getKeyValue();
        if (material == null || material.trim().isEmpty()) {
            return;
        }
        if (isOwner && mayReturnMaterialToOwner(keymanage)) {
            return;
        }
        keymanage.setKeyValue(redactedEnvelope(keymanage));
    }

    /** 该密钥的材料是否允许返回给属主本人。 */
    public static boolean mayReturnMaterialToOwner(Keymanage keymanage) {
        if (keymanage == null) {
            return false;
        }
        if (!CERTIFICATELESS_TYPE.equals(keymanage.getEncrytType())) {
            // 对称 / 其他类型不在本系统的无证书流程里，不需要材料
            return false;
        }
        String name = keymanage.getEncrytName();
        return name != null && OWNER_MATERIAL_ALGORITHMS.contains(name);
    }

    /**
     * 公钥投影：只取公开部分。
     *
     * <ul>
     *   <li>SM2 → {@code finalPublicKey}（完整公钥 W_A；**不是** {@code partialKey}）</li>
     *   <li>SSCL → {@code SSCLKey}（用户公钥份额；**不带** {@code SSCLEA}）</li>
     *   <li>其他（含格算法）→ {@code ua}。格算法的 {@code key_value} 里是完整私钥，
     *       **绝不整体回退**。</li>
     * </ul>
     */
    public static String publicProjection(Keymanage keymanage) {
        if (keymanage == null) {
            return null;
        }
        String material = keymanage.getKeyValue();
        if (material != null && !material.trim().isEmpty()
            && CERTIFICATELESS_TYPE.equals(keymanage.getEncrytType())) {
            try {
                JSONObject payload = JSON.parseObject(material);
                if ("SM2".equals(keymanage.getEncrytName())) {
                    String value = payload.getString("finalPublicKey");
                    if (value != null && !value.trim().isEmpty()) {
                        return value.trim();
                    }
                } else if ("SSCL".equals(keymanage.getEncrytName())) {
                    String value = payload.getString("SSCLKey");
                    if (value != null && !value.trim().isEmpty()) {
                        return value.trim();
                    }
                }
            } catch (Exception ex) {
                log.warn("解析公钥失败: keyId={}, encrytName={}", keymanage.getKeyId(), keymanage.getEncrytName(), ex);
            }
        }
        String ua = keymanage.getUa();
        return (ua == null || ua.trim().isEmpty()) ? null : ua.trim();
    }

    /** 脱敏后用于替换 {@code keyValue} 的信封。 */
    private static String redactedEnvelope(Keymanage keymanage) {
        JSONObject envelope = new JSONObject();
        envelope.put("redacted", true);
        envelope.put("reason", "material_not_returned");
        String publicValue = publicProjection(keymanage);
        envelope.put("publicValue", publicValue == null ? "" : publicValue);
        return envelope.toJSONString();
    }
}