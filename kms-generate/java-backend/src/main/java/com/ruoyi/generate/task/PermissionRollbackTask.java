package com.ruoyi.generate.task;

import com.ruoyi.generate.service.PermissionRequestService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PermissionRollbackTask {
    private static final Logger log = LoggerFactory.getLogger(PermissionRollbackTask.class);

    private final PermissionRequestService permissionRequestService;

    public PermissionRollbackTask(PermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @Scheduled(fixedDelay = 60000)
    public void rollbackExpiredRequests() {
        int count = permissionRequestService.rollbackExpiredApprovedRequests();
        if (count > 0) {
            log.info("generate permission auto rollback count={}", count);
        }
    }
}
