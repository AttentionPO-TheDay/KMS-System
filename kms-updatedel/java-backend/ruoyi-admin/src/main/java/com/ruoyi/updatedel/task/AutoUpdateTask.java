package com.ruoyi.updatedel.task;

import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.LifecycleService;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class AutoUpdateTask {
    private static final Logger log = LoggerFactory.getLogger(AutoUpdateTask.class);

    private final LifecycleService lifecycleService;

    public AutoUpdateTask(LifecycleService lifecycleService) {
        this.lifecycleService = lifecycleService;
    }

    @Scheduled(fixedDelayString = "${kms.lifecycle.auto-update.scan-delay-ms:60000}")
    public void executeAutoUpdate() {
        List<Keymanage> candidates = lifecycleService.listAutoUpdateCandidates();
        int successCount = 0;
        for (Keymanage candidate : candidates) {
            try {
                lifecycleService.rotateKey(candidate, "AUTO");
                successCount++;
            } catch (Exception ex) {
                log.warn("auto update failed, keyId={}", candidate.getKeyId(), ex);
            }
        }
        if (successCount > 0) {
            log.info("auto update executed count={}", successCount);
        }
    }
}
