package com.ruoyi.generate.service;

import com.ruoyi.generate.domain.PermissionRequest;

import java.util.List;

public interface IPermissionRequestService {
    List<PermissionRequest> list(Long userId, String status);

    PermissionRequest get(Long requestId);

    void delete(Long requestId);

    void submit(PermissionRequest request);

    void approve(Long requestId, String approveBy, String approveNote);

    void reject(Long requestId, String approveBy, String approveNote);

    void rollback(Long requestId);

    int rollbackExpiredApprovedRequests();

    boolean hasActivePermission(Long userId, String featureCode);
}
