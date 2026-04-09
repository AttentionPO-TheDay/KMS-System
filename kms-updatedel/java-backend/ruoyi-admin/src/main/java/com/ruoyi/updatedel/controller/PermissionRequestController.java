package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.updatedel.domain.PermissionRequest;
import com.ruoyi.updatedel.service.PermissionRequestService;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/permission/request")
public class PermissionRequestController extends BaseController {
    private final PermissionRequestService permissionRequestService;

    public PermissionRequestController(PermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(PermissionRequest query) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            query.setUserId(getUserId());
        }
        startPage();
        return getDataTable(permissionRequestService.list(query));
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{requestId}")
    public AjaxResult getInfo(@PathVariable Long requestId) {
        return permissionRequestService.findById(requestId)
            .map(request -> {
                if (!canAccess(request)) {
                    return AjaxResult.error("无权访问该权限申请");
                }
                return AjaxResult.success(request);
            })
            .orElseGet(() -> AjaxResult.error("权限申请不存在: " + requestId));
    }

    @PreAuthorize("isAuthenticated()")
    @PostMapping("/submit")
    public AjaxResult submit(@RequestBody PermissionRequest request) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            request.setUserId(getUserId());
            request.setUserName(getUsername());
        }
        return AjaxResult.success("提交成功", permissionRequestService.submit(request));
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/approve/{requestId}")
    public AjaxResult approve(@PathVariable Long requestId, @RequestBody(required = false) Map<String, String> body) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            return AjaxResult.error("无权审批权限申请");
        }
        permissionRequestService.approve(requestId, getUsername(), body == null ? null : body.get("approveNote"));
        return AjaxResult.success();
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/reject/{requestId}")
    public AjaxResult reject(@PathVariable Long requestId, @RequestBody(required = false) Map<String, String> body) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            return AjaxResult.error("无权审批权限申请");
        }
        permissionRequestService.reject(requestId, getUsername(), body == null ? null : body.get("approveNote"));
        return AjaxResult.success();
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/rollback/{requestId}")
    public AjaxResult rollback(@PathVariable Long requestId) {
        PermissionRequest request = permissionRequestService.findById(requestId).orElse(null);
        if (request == null) {
            return AjaxResult.error("权限申请不存在: " + requestId);
        }
        if (!canAccess(request)) {
            return AjaxResult.error("无权回退该权限申请");
        }
        permissionRequestService.rollback(requestId);
        return AjaxResult.success();
    }

    @PreAuthorize("isAuthenticated()")
    @DeleteMapping("/{requestId}")
    public AjaxResult delete(@PathVariable Long requestId) {
        PermissionRequest request = permissionRequestService.findById(requestId).orElse(null);
        if (request == null) {
            return AjaxResult.error("权限申请不存在: " + requestId);
        }
        if (!canAccess(request)) {
            return AjaxResult.error("无权删除该权限申请");
        }
        permissionRequestService.delete(requestId);
        return AjaxResult.success();
    }

    private boolean canAccess(PermissionRequest request) {
        return SecurityUtils.isAdmin(getUserId()) || getUserId().equals(request.getUserId());
    }
}
