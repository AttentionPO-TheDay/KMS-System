package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.updatedel.domain.PermissionRequest;
import com.ruoyi.updatedel.service.PermissionRequestService;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
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

    @GetMapping("/list")
    public TableDataInfo list(PermissionRequest query) {
        startPage();
        return getDataTable(permissionRequestService.list(query));
    }

    @GetMapping("/{requestId}")
    public AjaxResult getInfo(@PathVariable Long requestId) {
        return permissionRequestService.findById(requestId)
            .map(AjaxResult::success)
            .orElseGet(() -> AjaxResult.error("权限申请不存在: " + requestId));
    }

    @PostMapping("/submit")
    public AjaxResult submit(@RequestBody PermissionRequest request) {
        return AjaxResult.success("提交成功", permissionRequestService.submit(request));
    }

    @PutMapping("/approve/{requestId}")
    public AjaxResult approve(@PathVariable Long requestId, @RequestBody(required = false) Map<String, String> body) {
        permissionRequestService.approve(requestId, getUsername(), body == null ? null : body.get("approveNote"));
        return AjaxResult.success();
    }

    @PutMapping("/reject/{requestId}")
    public AjaxResult reject(@PathVariable Long requestId, @RequestBody(required = false) Map<String, String> body) {
        permissionRequestService.reject(requestId, getUsername(), body == null ? null : body.get("approveNote"));
        return AjaxResult.success();
    }

    @PutMapping("/rollback/{requestId}")
    public AjaxResult rollback(@PathVariable Long requestId) {
        permissionRequestService.rollback(requestId);
        return AjaxResult.success();
    }
}
