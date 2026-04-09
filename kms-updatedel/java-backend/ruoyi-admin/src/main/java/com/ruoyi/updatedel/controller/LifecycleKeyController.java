package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.LifecycleService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lifecycle/keymanage")
public class LifecycleKeyController extends BaseController {
    private final LifecycleService lifecycleService;

    public LifecycleKeyController(LifecycleService lifecycleService) {
        this.lifecycleService = lifecycleService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(Keymanage query) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            query.setUserId(getUserId());
        }
        query.setStatus(normalizeStatusQuery(query.getStatus()));
        startPage();
        return getDataTable(lifecycleService.list(query));
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}")
    public AjaxResult getInfo(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                return AjaxResult.success(key);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
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
        if (request.getEncrytType() == null && request.getEncrytName() == null && request.getKeyName() == null
            && request.getKeyUse() == null && request.getKeyDomain() == null && request.getUa() == null
            && request.getUserName() == null) {
            if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
                return AjaxResult.error("该密钥已被回收，无法修改自动更新状态");
            }
            if (!canManageAutoUpdate()) {
                return AjaxResult.error("当前用户没有自动更新操作权限");
            }
            lifecycleService.updateAutoUpdate(request.getKeyId(), request.getAutoUpdate());
            return AjaxResult.success("自动更新状态修改成功", lifecycleService.findById(request.getKeyId()).orElse(null));
        }
        return AjaxResult.success("密钥更新成功", lifecycleService.rotateKey(request));
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
        lifecycleService.revokeKey(keyId);
        return AjaxResult.success("密钥回收成功", keyId);
    }

    private boolean canAccess(Keymanage keymanage) {
        return SecurityUtils.isAdmin(getUserId()) || getUserId().equals(keymanage.getUserId());
    }

    private boolean canManageAutoUpdate() {
        return getLoginUser() != null
            && getLoginUser().getUser() != null
            && getLoginUser().getUser().getRoleLevel() != null
            && getLoginUser().getUser().getRoleLevel() <= 0;
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
