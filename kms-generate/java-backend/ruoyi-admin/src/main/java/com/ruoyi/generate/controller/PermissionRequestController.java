package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.generate.domain.PermissionRequest;
import com.ruoyi.generate.service.IPermissionRequestService;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/permission/request")
public class PermissionRequestController extends BaseController {
    private final IPermissionRequestService permissionRequestService;

    public PermissionRequestController(IPermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @GetMapping("/list")
    public TableDataInfo list(@RequestParam(required = false) Long userId,
                              @RequestParam(required = false) String status) {
        List<PermissionRequest> rows = permissionRequestService.list(userId, status);
        TableDataInfo table = new TableDataInfo();
        table.setCode(200);
        table.setMsg("查询成功");
        table.setRows(rows);
        table.setTotal(rows.size());
        return table;
    }

    @GetMapping("/{requestId}")
    public AjaxResult get(@PathVariable Long requestId) {
        PermissionRequest data = permissionRequestService.get(requestId);
        if (data == null) {
            return AjaxResult.error(404, "申请不存在");
        }
        return AjaxResult.success("查询成功", data);
    }

    @PostMapping("/submit")
    public AjaxResult submit(@RequestBody PermissionRequest request) {
        try {
            permissionRequestService.submit(request);
            return success("提交成功");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PutMapping("/approve/{requestId}")
    public AjaxResult approve(@PathVariable Long requestId, @RequestBody PermissionRequest request) {
        try {
            permissionRequestService.approve(requestId, request.getApproveBy(), request.getApproveNote());
            return success("审批通过");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PutMapping("/reject/{requestId}")
    public AjaxResult reject(@PathVariable Long requestId, @RequestBody PermissionRequest request) {
        try {
            permissionRequestService.reject(requestId, request.getApproveBy(), request.getApproveNote());
            return success("审批拒绝");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @PutMapping("/rollback/{requestId}")
    public AjaxResult rollback(@PathVariable Long requestId) {
        try {
            permissionRequestService.rollback(requestId);
            return success("回退成功");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }

    @DeleteMapping("/{requestId}")
    public AjaxResult delete(@PathVariable Long requestId) {
        try {
            permissionRequestService.delete(requestId);
            return success("删除成功");
        } catch (IllegalArgumentException ex) {
            return error(ex.getMessage());
        }
    }
}
