package com.ruoyi.permission.controller;

import java.util.List;
import javax.servlet.http.HttpServletResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.permission.domain.PermissionRequest;
import com.ruoyi.permission.service.IPermissionRequestService;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.common.core.page.TableDataInfo;

/**
 * 权限申请Controller
 * 
 * @author ruoyi
 * @date 2025-12-08
 */
@RestController
@RequestMapping("/permission/request")
public class PermissionRequestController extends BaseController {
    @Autowired
    private IPermissionRequestService permissionRequestService;

    /**
     * 查询权限申请列表
     */
    @GetMapping("/list")
    public TableDataInfo list(PermissionRequest permissionRequest) {
        startPage();
        List<PermissionRequest> list = permissionRequestService.selectPermissionRequestList(permissionRequest);
        return getDataTable(list);
    }

    /**
     * 导出权限申请列表
     */
    @PreAuthorize("@ss.hasPermi('permission:request:export')")
    @Log(title = "权限申请", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, PermissionRequest permissionRequest) {
        List<PermissionRequest> list = permissionRequestService.selectPermissionRequestList(permissionRequest);
        ExcelUtil<PermissionRequest> util = new ExcelUtil<PermissionRequest>(PermissionRequest.class);
        util.exportExcel(response, list, "权限申请数据");
    }

    /**
     * 获取权限申请详细信息
     */
    @GetMapping(value = "/{requestId}")
    public AjaxResult getInfo(@PathVariable("requestId") Long requestId) {
        return success(permissionRequestService.selectPermissionRequestByRequestId(requestId));
    }

    /**
     * 新增权限申请（用户提交申请）
     */
    @Log(title = "权限申请", businessType = BusinessType.INSERT)
    @PostMapping("/submit")
    public AjaxResult submit(@RequestBody PermissionRequest permissionRequest) {
        return toAjax(permissionRequestService.insertPermissionRequest(permissionRequest));
    }

    /**
     * 修改权限申请
     */
    @PreAuthorize("@ss.hasPermi('permission:request:edit')")
    @Log(title = "权限申请", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody PermissionRequest permissionRequest) {
        return toAjax(permissionRequestService.updatePermissionRequest(permissionRequest));
    }

    /**
     * 审批通过权限申请
     */
    @PreAuthorize("@ss.hasPermi('permission:request:approve')")
    @Log(title = "权限审批", businessType = BusinessType.UPDATE)
    @PutMapping("/approve/{requestId}")
    public AjaxResult approve(@PathVariable("requestId") Long requestId, @RequestBody PermissionRequest request) {
        String approveBy = getUsername();
        String approveNote = request.getApproveNote();
        return toAjax(permissionRequestService.approveRequest(requestId, approveBy, approveNote));
    }

    /**
     * 审批拒绝权限申请
     */
    @PreAuthorize("@ss.hasPermi('permission:request:approve')")
    @Log(title = "权限审批", businessType = BusinessType.UPDATE)
    @PutMapping("/reject/{requestId}")
    public AjaxResult reject(@PathVariable("requestId") Long requestId, @RequestBody PermissionRequest request) {
        String approveBy = getUsername();
        String approveNote = request.getApproveNote();
        return toAjax(permissionRequestService.rejectRequest(requestId, approveBy, approveNote));
    }

    /**
     * 回退用户权限
     */
    @Log(title = "权限回退", businessType = BusinessType.UPDATE)
    @PutMapping("/rollback/{requestId}")
    public AjaxResult rollback(@PathVariable("requestId") Long requestId) {
        System.out.println("[CONTROLLER] ========== 收到回退请求 ==========");
        System.out.println("[CONTROLLER] Request ID: " + requestId);
        AjaxResult result = toAjax(permissionRequestService.rollbackPermission(requestId));
        System.out.println("[CONTROLLER] 回退结果: " + result);
        return result;
    }

    /**
     * 删除权限申请
     */
    @PreAuthorize("@ss.hasPermi('permission:request:remove')")
    @Log(title = "权限申请", businessType = BusinessType.DELETE)
    @DeleteMapping("/{requestIds}")
    public AjaxResult remove(@PathVariable Long[] requestIds) {
        return toAjax(permissionRequestService.deletePermissionRequestByRequestIds(requestIds));
    }
}
