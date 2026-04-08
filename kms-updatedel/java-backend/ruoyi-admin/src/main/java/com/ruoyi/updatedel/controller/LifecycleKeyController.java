package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.LifecycleService;
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

    @GetMapping("/list")
    public TableDataInfo list(Keymanage query) {
        startPage();
        return getDataTable(lifecycleService.list(query));
    }

    @GetMapping("/{keyId}")
    public AjaxResult getInfo(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(AjaxResult::success)
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    @PutMapping
    public AjaxResult update(@RequestBody Keymanage request) {
        if (request.getKeyId() == null) {
            return AjaxResult.error("keyId 不能为空");
        }
        if (request.getEncrytType() == null && request.getEncrytName() == null && request.getKeyName() == null
            && request.getKeyUse() == null && request.getKeyDomain() == null && request.getUa() == null
            && request.getUserName() == null) {
            lifecycleService.updateAutoUpdate(request.getKeyId(), request.getAutoUpdate());
            return AjaxResult.success("自动更新状态修改成功", lifecycleService.findById(request.getKeyId()).orElse(null));
        }
        return AjaxResult.success("密钥更新成功", lifecycleService.rotateKey(request));
    }

    @PutMapping("/auto-update")
    public AjaxResult updateAutoUpdate(@RequestBody Keymanage request) {
        if (request.getKeyId() == null) {
            return AjaxResult.error("keyId 不能为空");
        }
        lifecycleService.updateAutoUpdate(request.getKeyId(), request.getAutoUpdate());
        return AjaxResult.success("自动更新状态修改成功", lifecycleService.findById(request.getKeyId()).orElse(null));
    }

    @DeleteMapping("/{keyId}")
    public AjaxResult revoke(@PathVariable Long keyId) {
        lifecycleService.revokeKey(keyId);
        return AjaxResult.success("密钥回收成功", keyId);
    }
}
