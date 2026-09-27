package com.ruoyi.updatedel.controller;

import com.ruoyi.common.constant.CacheConstants;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.utils.StringUtils;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import com.ruoyi.updatedel.service.LifecycleService;
import com.ruoyi.updatedel.service.UserPublicKeyService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/lifecycle")
public class InternalLifecycleController {
    private final LifecycleService lifecycleService;
    private final KeyOperationRecordService keyOperationRecordService;
    private final RedisCache redisCache;
    private final UserPublicKeyService userPublicKeyService;
    private final com.ruoyi.framework.web.service.TokenService tokenService;
    private final com.ruoyi.updatedel.mapper.SysUserMapper sysUserMapper;

    // 内部 Token 必须由环境变量 INTERNAL_TOKEN 注入，无默认值（历史默认值为公开值）。
    @Value("${kms.go-backend.internal-token}")
    private String internalToken;

    public InternalLifecycleController(LifecycleService lifecycleService,
                                       KeyOperationRecordService keyOperationRecordService,
                                       RedisCache redisCache,
                                       UserPublicKeyService userPublicKeyService,
                                       com.ruoyi.framework.web.service.TokenService tokenService,
                                       com.ruoyi.updatedel.mapper.SysUserMapper sysUserMapper) {
        this.lifecycleService = lifecycleService;
        this.keyOperationRecordService = keyOperationRecordService;
        this.redisCache = redisCache;
        this.userPublicKeyService = userPublicKeyService;
        this.tokenService = tokenService;
        this.sysUserMapper = sysUserMapper;
    }

    /**
     * 取某把密钥的**加密目标点** {@code P_A}（计划 §5.2，供分发模块的服务令牌调用）。
     *
     * <h2>为什么分发模块必须用这个接口，而不是自己去读 key_value</h2>
     * 用户实际可解的公钥点是 {@code P_A = W_A + λ·P_pub}，**不是** {@code key_value} 里
     * 任何一个字段。拿 {@code finalPublicKey} 加密会做出**谁都打不开**的信封（§3.2.3）。
     * 这条推导只有一份（{@code UpdatedelChainService.calculatePA}），
     * 由本接口统一对外提供，避免分发侧"自己算一遍"算错。
     *
     * <p>同时这里也承担 D17 的服务端收窄：非 SM2/SSCL、已回收、材料不可用的密钥
     * 一律返回 {@code ok=false}，让分发在服务端就被拦住。
     *
     * <h2>鉴权说明</h2>
     * 复用 {@code X-Internal-Token}（与 Go↔Java 内部通道同一把、由 compose 注入的
     * `INTERNAL_TOKEN`）。计划原本写的是"服务令牌"，但仓库里既有的
     * {@code X-KMS-Service-Token} 只用于**入站**保护 pqkds 自己的接口，
     * 并没有 KMS 侧的对应实现；为了不新造一套并行的凭据体系，这里复用已有通道。
     */
    @GetMapping("/user-public-key")
    public Map<String, Object> userPublicKey(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                             @RequestParam("keyId") Long keyId) {
        requireAuthorized(token);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", userPublicKeyService.describe(keyId));
        return payload;
    }

    @GetMapping("/key-status")
    public Map<String, Object> keyStatus(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                         @RequestParam("keyIds") List<Long> keyIds) {
        requireAuthorized(token);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Long keyId : keyIds) {
            Keymanage key = lifecycleService.findById(keyId).orElse(null);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("keyId", keyId);
            item.put("exists", key != null);
            item.put("status", key == null ? null : key.getStatus());
            item.put("chainStatus", key == null ? null : key.getChainStatus());
            item.put("updatedAt", key == null ? null : key.getUpdTime());
            items.add(item);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", items);
        return payload;
    }

    @GetMapping("/batch-proof")
    public Map<String, Object> batchProof(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                          @RequestParam("batchId") String batchId,
                                          @RequestParam(value = "actionType", defaultValue = "UPDATE") String actionType) {
        requireAuthorized(token);
        List<KeyOperationRecord> records = keyOperationRecordService.listBatchProofRecords(batchId, actionType);

        int expectedCount = 0;
        String batchRoot = null;
        String verifyStatus = null;
        String verifyMessage = null;
        boolean allCommitmentsPresent = true;
        boolean allConsistencyHashesPresent = true;
        Map<Integer, Boolean> indexSeen = new LinkedHashMap<>();
        boolean duplicateNodeIndex = false;

        for (KeyOperationRecord record : records) {
            if (record.getExpectedCount() != null && record.getExpectedCount() > expectedCount) {
                expectedCount = record.getExpectedCount();
            }
            if (batchRoot == null && record.getBatchRoot() != null) {
                batchRoot = record.getBatchRoot();
            }
            if (verifyStatus == null && record.getVerifyStatus() != null) {
                verifyStatus = record.getVerifyStatus();
            }
            if (verifyMessage == null && record.getVerifyMessage() != null) {
                verifyMessage = record.getVerifyMessage();
            }
            if (record.getCommitment() == null || record.getCommitment().trim().isEmpty()) {
                allCommitmentsPresent = false;
            }
            if (record.getConsistencyHash() == null || record.getConsistencyHash().trim().isEmpty()) {
                allConsistencyHashesPresent = false;
            }
            Integer nodeIndex = record.getNodeIndex();
            if (nodeIndex != null) {
                if (indexSeen.containsKey(nodeIndex)) {
                    duplicateNodeIndex = true;
                }
                indexSeen.put(nodeIndex, true);
            }
        }
        if (expectedCount <= 0) {
            expectedCount = records.size();
        }

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("batchId", batchId);
        summary.put("actionType", actionType);
        summary.put("expectedCount", expectedCount);
        summary.put("receivedCount", records.size());
        summary.put("batchRoot", batchRoot);
        summary.put("verifyStatus", verifyStatus);
        summary.put("verifyMessage", verifyMessage);
        summary.put("allCommitmentsPresent", allCommitmentsPresent);
        summary.put("allConsistencyHashesPresent", allConsistencyHashesPresent);
        summary.put("duplicateNodeIndex", duplicateNodeIndex);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("summary", summary);
        payload.put("data", records);
        return payload;
    }

    @PostMapping("/security/reset-blacklist")
    public Object resetBlacklist(@RequestHeader(value = "X-Internal-Token", required = false) String token) {
        requireAuthorized(token);
        com.ruoyi.framework.security.filter.SmartSecurityFilter.clearBlacklist();
        com.ruoyi.framework.security.filter.SmartSecurityFilter.clearAccessPatterns();
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("code", 200);
        map.put("msg", "success");
        return map;
    }

    @PostMapping("/security/reset-login-lock")
    public Object resetLoginLock(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                 @RequestParam(value = "username", required = false) String username) {
        requireAuthorized(token);
        if (StringUtils.isNotEmpty(username)) {
            redisCache.deleteObject(CacheConstants.PWD_ERR_CNT_KEY + username);
        } else {
            java.util.Collection<String> keys = redisCache.keys(CacheConstants.PWD_ERR_CNT_KEY + "*");
            if (keys != null && !keys.isEmpty()) {
                redisCache.deleteObject(keys);
            }
        }
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("code", 200);
        map.put("msg", "success");
        return map;
    }

    /**
     * 令牌自省：把调用方带来的**用户令牌**换成 `kms.sys_user` 身份（D7 的身份桥接）。
     *
     * <h2>为什么必须有这个接口</h2>
     * 分发模块（Django）要与主 KMS 共享同一套身份，但两边各有自己的登录体系：
     * KMS 用 `kms.sys_user`，Django 用 `dvadmin_system_users`。实测发现 pqkds 的视图
     * **全部是 `AllowAny`**，也就是说那边**今天根本拿不到用户身份** ——
     * 而 §5.1 要求"`user_id` 一律取自令牌，禁止从请求参数取"。
     * 没有这个桥接，那四个用户接口要么做不出来，要么只能信前端传的 user_id（可越权）。
     *
     * <h2>为什么不是"分发侧自己验签"</h2>
     * 自验签要把 JWT 签名密钥复制一份到 Django，等于把身份源变成两处；
     * 而 D7 明确 `dvadmin_system_users` 退化为"节点侧附属信息"、不再作为登录身份源。
     * 走自省则**只有 KMS 一处**解释令牌，分发侧只是消费结论。
     *
     * <h2>鉴权</h2>
     * 双重校验：`X-Internal-Token`（服务间，证明"调用方是分发模块"）
     * + `Authorization`（用户令牌，证明"用户是谁"）。**两者缺一不可** ——
     * 只有服务令牌的话，任何人拿到它就能冒充任意用户。
     *
     * @return {@code ok=true} 时带 `userId`/`userName`/`roleLevel`；
     *         令牌无效时 {@code ok=false} 且 `errorCode=TOKEN_INVALID`（不抛异常，
     *         让分发侧能把"未登录"与"服务异常"分开处理）
     */
    @GetMapping("/introspect")
    public Map<String, Object> introspect(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                          javax.servlet.http.HttpServletRequest request) {
        requireAuthorized(token);
        Map<String, Object> result = new LinkedHashMap<>();
        // 所有分支都必须收敛到同一个响应形状 `{data: {...}}`。
        // 早先的写法是成功时包 data、失败时直接返回顶层对象 ——
        // 调用方按 data 取值，失败时就拿到 undefined，反而看不出失败原因。
        try {
            com.ruoyi.common.core.domain.model.LoginUser loginUser = tokenService.getLoginUser(request);
            if (loginUser == null || loginUser.getUserId() == null) {
                result.put("ok", false);
                result.put("errorCode", "TOKEN_INVALID");
                result.put("errorMessage", "令牌无效或已过期");
                return wrapData(result);
            }
            result.put("ok", true);
            result.put("userId", loginUser.getUserId());
            result.put("userName", loginUser.getUsername());
            // 角色层级是"管理员/普通用户"的分流依据（D9）。取不到就留空，
            // 让分发侧按"最小权限"处理，而不是默认放行成管理员。
            com.ruoyi.common.core.domain.entity.SysUser sysUser = loginUser.getUser();
            if (sysUser != null) {
                result.put("roleLevel", sysUser.getRoleLevel());
            }
        } catch (Exception ex) {
            // 令牌无效是**预期内**的输入，不该变成 500；如实返回让调用方区分处理
            result.put("ok", false);
            result.put("errorCode", "TOKEN_INVALID");
            result.put("errorMessage", "令牌无效或已过期");
        }
        return wrapData(result);
    }

    /**
     * 账号列表（供管理端的「用户选择器」用，计划 §5.2 / P3 步骤 10）。
     *
     * <h2>为什么不让分发模块直接读 kms.sys_user</h2>
     * 主身份源是 `kms.sys_user`（D7），但"谁能读账号列表"这件事应当由**拥有身份的
     * 那一侧**决定。让 Django 跨库 select 会把鉴权判断散到两个服务里，
     * 而且跨库查询没有外键、没有权限边界，日后改表结构会两边同时坏。
     * 走接口则只有一处解释账号数据。
     *
     * <h2>返回字段刻意最小化</h2>
     * 只有 `userId` / `userName` / `roleLevel` —— **不含口令哈希**。
     * 账号列表本身就可被用来枚举系统里有哪些人，能少给就少给。
     *
     * @param keyword 可选，管理员主动搜索时按用户名模糊匹配
     */
    @GetMapping("/users")
    public Map<String, Object> users(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                     @RequestParam(value = "keyword", required = false) String keyword) {
        requireAuthorized(token);
        List<Map<String, Object>> items = new ArrayList<>();
        for (com.ruoyi.updatedel.domain.SysUser user : sysUserMapper.selectUserList(keyword)) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("userId", user.getUserId());
            item.put("userName", user.getUserName());
            item.put("roleLevel", user.getRoleLevel());
            items.add(item);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", items);
        return payload;
    }

    private Map<String, Object> wrapData(Map<String, Object> data) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", data);
        return payload;
    }

    private void requireAuthorized(String token) {
        if (token == null || !internalToken.equals(token)) {
            throw new IllegalArgumentException("invalid internal token");
        }
    }
}
