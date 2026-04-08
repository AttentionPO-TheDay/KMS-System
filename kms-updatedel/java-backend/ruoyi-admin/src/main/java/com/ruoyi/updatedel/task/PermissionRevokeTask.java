package com.ruoyi.updatedel.task;

import com.ruoyi.updatedel.service.PermissionRequestService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PermissionRevokeTask {
    private static final Logger log = LoggerFactory.getLogger(PermissionRevokeTask.class);

    private final PermissionRequestService permissionRequestService;

    public PermissionRevokeTask(PermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @Scheduled(fixedDelay = 60000)
    public void revokeExpiredPermissions() {
        int rollbackCount = permissionRequestService.rollbackExpiredApprovedRequests();
        if (rollbackCount > 0) {
            log.info("permission auto rollback count={}", rollbackCount);
        }
    }
}
