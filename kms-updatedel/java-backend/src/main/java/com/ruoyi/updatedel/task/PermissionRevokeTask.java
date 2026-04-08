package com.ruoyi.updatedel.task;

import com.ruoyi.updatedel.domain.PermissionRequest;
import com.ruoyi.updatedel.service.PermissionRequestService;
import java.util.Date;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PermissionRevokeTask {
    private static final Logger log = LoggerFactory.getLogger(PermissionRevokeTask.class);
    private static final long EXPIRE_MILLIS = 30L * 60L * 1000L;

    private final PermissionRequestService permissionRequestService;

    public PermissionRevokeTask(PermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @Scheduled(fixedDelay = 60000)
    public void revokeExpiredPermissions() {
        Date expireBefore = new Date(System.currentTimeMillis() - EXPIRE_MILLIS);
        List<PermissionRequest> expiredRequests = permissionRequestService.findExpiredApproved(expireBefore);
        for (PermissionRequest request : expiredRequests) {
            try {
                permissionRequestService.rollback(request.getRequestId());
                log.info("permission auto rollback success, requestId={}", request.getRequestId());
            } catch (Exception ex) {
                log.warn("permission auto rollback failed, requestId={}", request.getRequestId(), ex);
            }
        }
    }
}
