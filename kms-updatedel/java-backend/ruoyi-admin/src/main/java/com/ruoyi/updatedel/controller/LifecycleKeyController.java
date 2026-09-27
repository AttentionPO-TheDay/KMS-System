package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.updatedel.domain.KeyAnalysisResultDto;
import com.ruoyi.updatedel.domain.KeyHealthResult;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.KeyHealthService;
import com.ruoyi.updatedel.service.KeyValueSanitizer;
import com.ruoyi.updatedel.service.LifecycleService;
import com.ruoyi.updatedel.service.PermissionRequestService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/lifecycle/keymanage")
public class LifecycleKeyController extends BaseController {
    private static final Logger log = LoggerFactory.getLogger(LifecycleKeyController.class);

    private final LifecycleService lifecycleService;
    private final PermissionRequestService permissionRequestService;
    private final KeyHealthService keyHealthService;

    public LifecycleKeyController(LifecycleService lifecycleService,
                                  PermissionRequestService permissionRequestService,
                                  KeyHealthService keyHealthService) {
        this.lifecycleService = lifecycleService;
        this.permissionRequestService = permissionRequestService;
        this.keyHealthService = keyHealthService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(Keymanage query) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            query.setUserId(getUserId());
        }
        query.setStatus(normalizeStatusQuery(query.getStatus()));
        startPage();
        List<Keymanage> list = lifecycleService.list(query);
        // 列表一律不带密钥材料（见 KeyValueSanitizer 的说明）。
        // 已核对现网页面：生命周期相关的列表都不消费 keyValue；
        // 「更新」「安全分析」走的是更新响应与详情接口。
        KeyValueSanitizer.stripMaterial(list);
        return getDataTable(list);
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}")
    public AjaxResult getInfo(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                KeyValueSanitizer.sanitizeDetail(key, isOwner);
                return AjaxResult.success(key);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    /**
     * 阶段 4（文档 §5.2）：历史版本列表。
     *
     * <p>准入与脱敏必须和 {@link #getInfo} **完全一致** —— 历史快照里同样含
     * KGC 部分密钥（{@code key_value}）与公钥份额（{@code ua}）。
     * 这里若省掉 {@code canAccess} 或 {@code sanitizeDetail}，
     * 就等于开了一条"用别人 key_id 读其历史密钥材料"的旁路。
     *
     * <p>按版本号倒序返回，**不含当前版本**（当前版本走 {@code /{keyId}}）。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}/versions")
    public AjaxResult getVersionHistory(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                List<Keymanage> history = lifecycleService.findVersionHistory(keyId);
                for (Keymanage snapshot : history) {
                    KeyValueSanitizer.sanitizeDetail(snapshot, isOwner);
                }
                return AjaxResult.success(history);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    /**
     * 阶段 7（文档 §8.1 + §8.2）：单把密钥的健康检查。
     *
     * <p>一致性检查与异常检测合并成一个接口 —— 两者读同一份数据，
     * 分开只会把同样的表扫两遍，且可能给出互相矛盾的结论。
     *
     * <p>准入与 {@link #getInfo} 一致：健康检查会读到 ua/keyValue 的存在与长度
     * 并回显，不校验属主就成了"用别人 keyId 探测其密钥材料是否齐备"的旁路。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/health/{keyId}")
    public AjaxResult getHealth(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                KeyHealthResult result = keyHealthService.check(keyId);
                if (result == null) {
                    return AjaxResult.error("密钥不存在: " + keyId);
                }
                // 观测值里含 ua/keyValue 的长度信息；非属主只保留结论，
                // 去掉带材料细节的观测，避免侧面泄露。
                boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                if (!isOwner) {
                    result.getObservations().removeIf(o -> o.contains("ua ") || o.contains("keyValue "));
                }
                return AjaxResult.success(result);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/analysis/{keyId}")
    public AjaxResult getAnalysis(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权分析该密钥数据");
                }
                try {
                    KeyAnalysisResultDto analysis = lifecycleService.getAssociationAnalysis(keyId);
                    // 该 DTO 的 baseInfo 里嵌着整条 Keymanage（含 key_value），同样要脱敏，
                    // 否则"安全分析"会变成绕过列表脱敏的后门。
                    if (analysis != null && analysis.getBaseInfo() != null) {
                        boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                        KeyValueSanitizer.sanitizeDetail(analysis.getBaseInfo(), isOwner);
                    }
                    return AjaxResult.success(analysis);
                } catch (Exception e) {
                    log.error("密钥关联分析异常: keyId={}", keyId, e);
                    return AjaxResult.error("分析失败: " + e.getMessage());
                }
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    @PreAuthorize("isAuthenticated()")
    @PostMapping
    public AjaxResult create(@RequestBody Keymanage request) {
        try {
            if (request.getUserId() == null) {
                request.setUserId(getUserId());
            }
            if (request.getUserName() == null || request.getUserName().trim().isEmpty()) {
                request.setUserName(getLoginUser().getUser().getUserName());
            }
            log.info("密钥新建: userId={}, encrytName={}", request.getUserId(), request.getEncrytName());
            Keymanage created = lifecycleService.createKey(request);
            return AjaxResult.success("密钥创建成功", created);
        } catch (Exception e) {
            log.error("密钥新建异常", e);
            return AjaxResult.error("密钥创建失败: " + e.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping
    public AjaxResult update(@RequestBody Keymanage request) {
        if (request.getKeyId() == null) {
            return AjaxResult.error("keyId 不能为空");
        }
        Keymanage current = lifecycleService.findById(request.getKeyId()).orElse(null);
        if (current == null) {
            return AjaxResult.error("密钥不存在: " + request.getKeyId());
        }
        if (!canAccess(current)) {
            return AjaxResult.error("无权修改该密钥");
        }

        // 只有当 autoUpdate 的**值真的发生变化**时才要求自动更新权限。
        //
        // 原实现是"只要请求带了这个字段就要权限"，而两个前端的"更新密钥"弹窗
        // 都会把开关当前值一并提交（恒非空），于是只想改密钥名称的用户会被拦下，
        // 报错还是"当前用户没有自动更新操作权限" —— 与他在做的事对不上
        // （2026-09-24 用户截图）。
        //
        // 防绕过的本意保留：想借"顺手改个元数据"把自动更新打开，仍然会被拦。
        if (lifecycleService.changesAutoUpdate(current, request.getAutoUpdate()) && !canManageAutoUpdate()) {
            return AjaxResult.error("当前用户没有自动更新操作权限");
        }

        // 分流依据：是否提供了新的用户部分公钥 ua。
        // 未提供 → 仅更新元数据（不重新生成密钥材料、version 不变）。
        // 提供   → 视为真正的密钥轮换，重新生成密钥材料并递增 version。
        if (!lifecycleService.requiresRotation(request)) {
            try {
                Keymanage updated = lifecycleService.updateMetadata(request);
                return AjaxResult.success("密钥信息更新成功", updated);
            } catch (IllegalStateException e) {
                log.warn("密钥信息更新失败: keyId={}, error={}", request.getKeyId(), e.getMessage());
                return AjaxResult.error(e.getMessage());
            }
        }

        // Synchronous key rotation — 调用方已提供新的 ua
        try {
            log.info("密钥轮换: keyId={}, userId={}", request.getKeyId(), getUserId());
            Keymanage rotated = lifecycleService.rotateKey(request);
            return AjaxResult.success("密钥轮换成功", rotated);
        } catch (IllegalStateException e) {
            log.warn("密钥轮换失败: keyId={}, error={}", request.getKeyId(), e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            log.error("密钥轮换异常: keyId={}", request.getKeyId(), e);
            return AjaxResult.error("密钥轮换失败: " + e.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/auto-update")
    public AjaxResult updateAutoUpdate(@RequestBody Keymanage request) {
        if (request.getKeyId() == null) {
            return AjaxResult.error("keyId 不能为空");
        }
        Keymanage current = lifecycleService.findById(request.getKeyId()).orElse(null);
        if (current == null) {
            return AjaxResult.error("密钥不存在: " + request.getKeyId());
        }
        if (!canAccess(current)) {
            return AjaxResult.error("无权修改该密钥");
        }
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            return AjaxResult.error("该密钥已被回收，无法修改自动更新状态");
        }
        if (!canManageAutoUpdate()) {
            return AjaxResult.error("当前用户没有自动更新操作权限");
        }
        lifecycleService.updateAutoUpdate(request.getKeyId(), request.getAutoUpdate());
        return AjaxResult.success("自动更新状态修改成功", lifecycleService.findById(request.getKeyId()).orElse(null));
    }

    @PreAuthorize("isAuthenticated()")
    @DeleteMapping("/{keyId}")
    public AjaxResult revoke(@PathVariable Long keyId) {
        Keymanage current = lifecycleService.findById(keyId).orElse(null);
        if (current == null) {
            return AjaxResult.error("密钥不存在: " + keyId);
        }
        if (!canAccess(current)) {
            return AjaxResult.error("无权回收该密钥");
        }
        // Synchronous revocation — directly call service
        try {
            log.info("密钥回收: keyId={}, userId={}", keyId, getUserId());
            lifecycleService.revokeKey(keyId);
            return AjaxResult.success("密钥回收成功", keyId);
        } catch (IllegalStateException e) {
            log.warn("密钥回收失败: keyId={}, error={}", keyId, e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            log.error("密钥回收异常: keyId={}", keyId, e);
            return AjaxResult.error("密钥回收失败: " + e.getMessage());
        }
    }

    private boolean canAccess(Keymanage keymanage) {
        if (keymanage == null) {
            return false;
        }
        Long ownerId = keymanage.getUserId();
        Long currentId = getUserId();
        return SecurityUtils.isAdmin(currentId) || ownerId != null && ownerId.equals(currentId);
    }

    private boolean canManageAutoUpdate() {
        boolean hasPermanentAccess = getLoginUser() != null
            && getLoginUser().getUser() != null
            && getLoginUser().getUser().getRoleLevel() != null
            && getLoginUser().getUser().getRoleLevel() <= 0;
        return hasPermanentAccess || permissionRequestService.hasActiveTemporaryPermission(getUserId());
    }

    private String normalizeStatusQuery(String status) {
        if (status == null) {
            return null;
        }
        switch (status.trim()) {
            case "Valid":
            case "Active":
                return "0";
            case "Frozen":
                return "1";
            case "Replaced":
            case "Rotated":
                return "2";
            case "Revoked":
                return "3";
            default:
                return status.trim();
        }
    }
}
