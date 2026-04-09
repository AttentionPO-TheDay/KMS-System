package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.domain.PermissionRequest;
import com.ruoyi.generate.service.IPermissionRequestService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/permission/request")
public class PermissionRequestController extends BaseController {
    private final IPermissionRequestService permissionRequestService;

    public PermissionRequestController(IPermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(@RequestParam(required = false) Long userId,
                              @RequestParam(required = false) String status) {
        if (!isCurrentAdmin()) {
            userId = getUserId();
        }
        List<PermissionRequest> rows = permissionRequestService.list(userId, status);
        TableDataInfo table = new TableDataInfo();
        table.setCode(200);
        table.setMsg("查询成功");
        table.setRows(rows);
        table.setTotal(rows.size());
        return table;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{requestId}")
    public AjaxResult get(@PathVariable Long requestId) {
        PermissionRequest data = permissionRequestService.get(requestId);
        if (data == null) {
            return AjaxResult.error(404, "申请不存在");
        }
        if (!isCurrentAdmin() && (data.getUserId() == null || !data.getUserId().equals(getUserId()))) {
            return AjaxResult.error("无权访问该申请");
        }
        return AjaxResult.success("查询成功", data);
    }

    @PreAuthorize("isAuthenticated()")
    @PostMapping("/submit")
    public AjaxResult submit(@RequestBody PermissionRequest request) {
        try {
            request.setUserId(getUserId());
            request.setUserName(getUsername());
            request.setOriginalLevel(SecurityUtils.getLoginUser().getUser().getRoleLevel());
            permissionRequestService.submit(request);
            return success("提交成功");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/approve/{requestId}")
    public AjaxResult approve(@PathVariable Long requestId, @RequestBody PermissionRequest request) {
        try {
            ensureAdmin();
            permissionRequestService.approve(requestId, getUsername(), request.getApproveNote());
            return success("审批通过");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/reject/{requestId}")
    public AjaxResult reject(@PathVariable Long requestId, @RequestBody PermissionRequest request) {
        try {
            ensureAdmin();
            permissionRequestService.reject(requestId, getUsername(), request.getApproveNote());
            return success("审批拒绝");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/rollback/{requestId}")
    public AjaxResult rollback(@PathVariable Long requestId) {
        try {
            PermissionRequest data = permissionRequestService.get(requestId);
            if (data == null) {
                return error("权限申请不存在");
            }
            if (!isCurrentAdmin() && (data.getUserId() == null || !data.getUserId().equals(getUserId()))) {
                return error("无权回退该申请");
            }
            permissionRequestService.rollback(requestId);
            return success("回退成功");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @DeleteMapping("/{requestId}")
    public AjaxResult delete(@PathVariable Long requestId) {
        try {
            PermissionRequest data = permissionRequestService.get(requestId);
            if (data == null) {
                return error("权限申请不存在");
            }
            if (!isCurrentAdmin() && (data.getUserId() == null || !data.getUserId().equals(getUserId()))) {
                return error("无权删除该申请");
            }
            permissionRequestService.delete(requestId);
            return success("删除成功");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    private boolean isCurrentAdmin() {
        return SecurityUtils.getLoginUser().getUser() != null && SecurityUtils.getLoginUser().getUser().isAdmin();
    }

    private void ensureAdmin() {
        if (!isCurrentAdmin()) {
            throw new IllegalArgumentException("仅管理员可执行审批操作");
        }
    }
}
