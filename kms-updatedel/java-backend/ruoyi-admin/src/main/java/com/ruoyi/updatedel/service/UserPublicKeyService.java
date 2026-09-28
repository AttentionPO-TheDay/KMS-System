package com.ruoyi.updatedel.service;

import com.ruoyi.common.crypto.KgcMasterSecret;
import com.ruoyi.updatedel.domain.Keymanage;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 对外提供「用户加密目标点」{@code P_A}（计划 §5.2 / P3 步骤 7）。
 *
 * <h2>为什么单独立一个服务而不是直接调链上服务</h2>
 * {@code P_A} 的推导只有一份，在 {@link UpdatedelChainService#calculatePA} 里。
 * 本类**只做转发与状态判定**，绝不自己再推一遍 —— 计划 §3.2.3 明确要求
 * "复用已有算式，不要另写一份推导"，因为写错一版就会做出**谁都打不开**的信封，
 * 而且症状是"用户解不开"，很难倒查到是加密目标选错了。
 *
 * <h2>为什么不直接把 {@code key_value} 给分发模块</h2>
 * {@code key_value} 里有 {@code partialKey}（私钥分片）、也可能有格算法的完整私钥。
 * 分发模块需要的只是**公开的加密目标点**，给多了就是泄露面。
 */
@Service
public class UserPublicKeyService {

    private static final Logger log = LoggerFactory.getLogger(UserPublicKeyService.class);

    /** 目前用户腿支持封装到哪些算法（D17 收窄：只有 SM2 / SSCL） */
    private static final java.util.Set<String> SUPPORTED_ALGORITHMS =
        new java.util.HashSet<>(java.util.Arrays.asList("SM2", "SSCL"));

    private final LifecycleService lifecycleService;
    private final UpdatedelChainService updatedelChainService;

    public UserPublicKeyService(LifecycleService lifecycleService,
                                UpdatedelChainService updatedelChainService) {
        this.lifecycleService = lifecycleService;
        this.updatedelChainService = updatedelChainService;
    }

    /** 单把密钥的加密目标点查询结果 */
    public Map<String, Object> describe(Long keyId) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("keyId", keyId);

        Optional<Keymanage> found = lifecycleService.findById(keyId);
        if (!found.isPresent()) {
            return fail(result, "KEY_NOT_FOUND", "密钥不存在: " + keyId);
        }
        Keymanage key = found.get();

        result.put("userId", key.getUserId());
        result.put("userName", key.getUserName());
        result.put("encrytName", key.getEncrytName());
        result.put("status", key.getStatus());
        // 版本号（阶段 4 / §8.6 补）：链上存证要求事件带 `key_version`，
        // 而分发侧要记的 KEY_DISTRIBUTED 正是经这个接口拿目标点的。
        // 缺了它，链上只能回答"哪把密钥被分发过"，回答不了"哪个版本" ——
        // 而轮换之后，"哪个版本"恰恰是审计要对照的那个维度。
        result.put("version", key.getVersion());
        result.put("msKeyId", key.getMsKeyId());
        result.put("algorithmVersion", key.getAlgorithmVersion());
        result.put("keyMaterialState", key.getKeyMaterialState());

        // 已回收的密钥不再作为分发目标 —— 让分发模块在服务端就被拦住，
        // 而不是等到用户解不开才发现。
        if ("3".equals(key.getStatus())) {
            return fail(result, "KEY_REVOKED", "该密钥已被回收，不能作为分发目标");
        }
        if (!SUPPORTED_ALGORITHMS.contains(key.getEncrytName())) {
            // D17：用户腿只允许 SM2 / SSCL。格算法不在其中，且它们的私钥在服务端，
            // 给出去就等于没有机密性可言。
            return fail(result, "ALGORITHM_NOT_SUPPORTED_FOR_USER_LEG",
                "算法 " + key.getEncrytName() + " 不可用于分发（用户腿仅支持 SM2 / SSCL）");
        }

        String publicKey = updatedelChainService.calculatePA(key);
        if (publicKey == null || publicKey.trim().isEmpty()) {
            // 这里必须显式失败：绝不回退到 finalPublicKey。
            // 用 W_A 加密出来的信封连用户自己都打不开（§3.2.3），
            // 静默回退会把"算不出来"变成一个更难查的"解不开"。
            log.warn("无法计算 P_A，拒绝返回加密目标: keyId={}, encrytName={}, msKeyId={}",
                keyId, key.getEncrytName(), key.getMsKeyId());
            return fail(result, "PA_CALC_FAILED",
                "无法计算该密钥的加密目标点 P_A（可能缺少 finalPublicKey/SSCLKey 或点不在曲线上）");
        }

        result.put("publicKey", publicKey.toLowerCase());
        result.put("publicKeyId", KgcMasterSecret.activeId());
        result.put("ok", true);
        return result;
    }

    private Map<String, Object> fail(Map<String, Object> result, String code, String message) {
        result.put("ok", false);
        result.put("errorCode", code);
        result.put("errorMessage", message);
        return result;
    }
}