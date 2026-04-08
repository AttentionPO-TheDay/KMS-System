package com.ruoyi.permission.task;

import com.ruoyi.permission.domain.PermissionRequest;
import com.ruoyi.permission.service.IPermissionRequestService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Date;
import java.util.List;

/**
 * 权限自动回收定时任务
 */
@Component
public class PermissionRevokeTask {

    @Autowired
    private IPermissionRequestService permissionRequestService;

    /**
     * 每分钟检查一次过期的权限
     */
    @Scheduled(fixedDelay = 60000)
    public void revokeExpiredPermissions() {
        // 查询所有已通过审批的申请
        PermissionRequest query = new PermissionRequest();
        query.setStatus("1"); // 已通过
        List<PermissionRequest> list = permissionRequestService.selectPermissionRequestList(query);

        long now = System.currentTimeMillis();
        // 30分钟 = 30 * 60 * 1000 毫秒
        long expireDuration = 30 * 60 * 1000;

        for (PermissionRequest request : list) {
            Date approveTime = request.getApproveTime();
            if (approveTime != null) {
                if (now - approveTime.getTime() > expireDuration) {
                    try {
                        System.out.println("自动回收权限: request_id=" + request.getRequestId());
                        permissionRequestService.rollbackPermission(request.getRequestId());
                    } catch (Exception e) {
                        System.err.println("自动回收失败 request_id=" + request.getRequestId() + ": " + e.getMessage());
                    }
                }
            }
        }
    }
}
