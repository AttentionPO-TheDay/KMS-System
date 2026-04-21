package com.ruoyi.updatedel.controller;

import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import com.ruoyi.updatedel.service.LifecycleService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;

@RestController
@RequestMapping("/internal/lifecycle")
public class InternalLifecycleController {
    private final LifecycleService lifecycleService;
    private final KeyOperationRecordService keyOperationRecordService;

    @Value("${kms.go-backend.internal-token:kms-generate-internal-secret-2026}")
    private String internalToken;

    public InternalLifecycleController(LifecycleService lifecycleService,
                                       KeyOperationRecordService keyOperationRecordService) {
        this.lifecycleService = lifecycleService;
        this.keyOperationRecordService = keyOperationRecordService;
    }

    @GetMapping("/key-status")
    public Map<String, Object> keyStatus(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                         @RequestParam("keyIds") List<Long> keyIds) {
        requireAuthorized(token);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Long keyId : keyIds) {
            Keymanage key = lifecycleService.findById(keyId).orElse(null);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("keyId", keyId);
            item.put("exists", key != null);
            item.put("status", key == null ? null : key.getStatus());
            item.put("chainStatus", key == null ? null : key.getChainStatus());
            item.put("updatedAt", key == null ? null : key.getUpdTime());
            items.add(item);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", items);
        return payload;
    }

    @GetMapping("/batch-proof")
    public Map<String, Object> batchProof(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                          @RequestParam("batchId") String batchId,
                                          @RequestParam(value = "actionType", defaultValue = "UPDATE") String actionType) {
        requireAuthorized(token);
        List<KeyOperationRecord> records = keyOperationRecordService.listBatchProofRecords(batchId, actionType);

        int expectedCount = 0;
        String batchRoot = null;
        String verifyStatus = null;
        String verifyMessage = null;
        boolean allCommitmentsPresent = true;
        boolean allConsistencyHashesPresent = true;
        Map<Integer, Boolean> indexSeen = new LinkedHashMap<>();
        boolean duplicateNodeIndex = false;

        for (KeyOperationRecord record : records) {
            if (record.getExpectedCount() != null && record.getExpectedCount() > expectedCount) {
                expectedCount = record.getExpectedCount();
            }
            if (batchRoot == null && record.getBatchRoot() != null) {
                batchRoot = record.getBatchRoot();
            }
            if (verifyStatus == null && record.getVerifyStatus() != null) {
                verifyStatus = record.getVerifyStatus();
            }
            if (verifyMessage == null && record.getVerifyMessage() != null) {
                verifyMessage = record.getVerifyMessage();
            }
            if (record.getCommitment() == null || record.getCommitment().trim().isEmpty()) {
                allCommitmentsPresent = false;
            }
            if (record.getConsistencyHash() == null || record.getConsistencyHash().trim().isEmpty()) {
                allConsistencyHashesPresent = false;
            }
            Integer nodeIndex = record.getNodeIndex();
            if (nodeIndex != null) {
                if (indexSeen.containsKey(nodeIndex)) {
                    duplicateNodeIndex = true;
                }
                indexSeen.put(nodeIndex, true);
            }
        }
        if (expectedCount <= 0) {
            expectedCount = records.size();
        }

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("batchId", batchId);
        summary.put("actionType", actionType);
        summary.put("expectedCount", expectedCount);
        summary.put("receivedCount", records.size());
        summary.put("batchRoot", batchRoot);
        summary.put("verifyStatus", verifyStatus);
        summary.put("verifyMessage", verifyMessage);
        summary.put("allCommitmentsPresent", allCommitmentsPresent);
        summary.put("allConsistencyHashesPresent", allConsistencyHashesPresent);
        summary.put("duplicateNodeIndex", duplicateNodeIndex);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("summary", summary);
        payload.put("data", records);
        return payload;
    }

    @PostMapping("/security/reset-blacklist")
    public Object resetBlacklist(@RequestHeader(value = "X-Internal-Token", required = false) String token) {
        requireAuthorized(token);
        com.ruoyi.framework.security.filter.SmartSecurityFilter.clearBlacklist();
        com.ruoyi.framework.security.filter.SmartSecurityFilter.clearAccessPatterns();
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("code", 200);
        map.put("msg", "success");
        return map;
    }

    @PostMapping("/security/reset-login-lock")
    public Object resetLoginLock(@RequestHeader(value = "X-Internal-Token", required = false) String token) {
        requireAuthorized(token);
        com.ruoyi.framework.security.service.LoginAttemptService loginAttemptService = com.ruoyi.common.utils.spring.SpringUtils.getBean(com.ruoyi.framework.security.service.LoginAttemptService.class);
        loginAttemptService.clearAll();
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("code", 200);
        map.put("msg", "success");
        return map;
    }

    private void requireAuthorized(String token) {
        if (token == null || !internalToken.equals(token)) {
            throw new IllegalArgumentException("invalid internal token");
        }
    }
}
