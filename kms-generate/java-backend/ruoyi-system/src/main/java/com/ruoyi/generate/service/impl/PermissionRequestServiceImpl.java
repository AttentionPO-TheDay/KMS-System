package com.ruoyi.generate.service.impl;

import com.ruoyi.generate.domain.PermissionRequest;
import com.ruoyi.generate.mapper.PermissionRequestMapper;
import com.ruoyi.generate.service.IPermissionRequestService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Date;
import java.util.List;

@Service
public class PermissionRequestServiceImpl implements IPermissionRequestService {
    private static final String SYSTEM_CODE = "generate";
    private static final String FEATURE_CODE = "PUBLIC_KEY_LIST";
    private static final String FEATURE_NAME = "查看公共密钥列表";

    @Autowired
    private PermissionRequestMapper permissionRequestMapper;

    @Override
    public List<PermissionRequest> list(Long userId, String status) {
        PermissionRequest query = new PermissionRequest();
        query.setSystemCode(SYSTEM_CODE);
        query.setUserId(userId);
        query.setStatus(status);
        return permissionRequestMapper.selectPermissionRequestList(query);
    }

    @Override
    public PermissionRequest get(Long requestId) {
        PermissionRequest request = permissionRequestMapper.selectPermissionRequestByRequestId(requestId);
        if (request == null || !SYSTEM_CODE.equals(request.getSystemCode())) {
            return null;
        }
        return request;
    }

    @Transactional
    @Override
    public void delete(Long requestId) {
        PermissionRequest request = get(requestId);
        if (request == null) {
            throw new IllegalArgumentException("权限申请不存在");
        }
        permissionRequestMapper.deletePermissionRequestByRequestId(requestId);
    }

    @Transactional
    @Override
    public void submit(PermissionRequest request) {
        validateSubmit(request);
        request.setSystemCode(SYSTEM_CODE);
        request.setFeatureCode(FEATURE_CODE);
        request.setFeatureName(FEATURE_NAME);
        request.setStatus("0");
        if (request.getOriginalLevel() != null && request.getOriginalLevel() == 1) {
            request.setOriginalLevel(2);
        }
        if (request.getIsTemp() == null) {
            request.setIsTemp(1);
        }
        request.setRequestTime(new Date());
        permissionRequestMapper.insertPermissionRequest(request);
    }

    @Transactional
    @Override
    public void approve(Long requestId, String approveBy, String approveNote) {
        PermissionRequest request = requirePending(requestId);
        Date now = new Date();
        request.setStatus("1");
        request.setApproveBy(blankToDefault(approveBy, "generate-admin"));
        request.setApproveTime(now);
        request.setApproveNote(approveNote);
        permissionRequestMapper.updatePermissionRequest(request);
        if (isTemporaryRequest(request) || !isTemporaryRequest(request)) {
            permissionRequestMapper.updateUserRoleLevel(request.getUserId(), request.getRequestLevel());
        }
    }

    @Transactional
    @Override
    public void reject(Long requestId, String approveBy, String approveNote) {
        PermissionRequest request = requirePending(requestId);
        Date now = new Date();
        request.setStatus("2");
        request.setApproveBy(blankToDefault(approveBy, "generate-admin"));
        request.setApproveTime(now);
        request.setApproveNote(approveNote);
        permissionRequestMapper.updatePermissionRequest(request);
    }

    @Transactional
    @Override
    public void rollback(Long requestId) {
        PermissionRequest request = get(requestId);
        if (request == null) {
            throw new IllegalArgumentException("权限申请不存在");
        }
        if (!"1".equals(request.getStatus())) {
            throw new IllegalArgumentException("当前申请未处于已通过状态，无法回退");
        }
        request.setStatus("3");
        request.setRollbackTime(new Date());
        permissionRequestMapper.updatePermissionRequest(request);

        if (isTemporaryRequest(request) || !isTemporaryRequest(request)) {
            PermissionRequest query = new PermissionRequest();
            query.setUserId(request.getUserId());
            query.setStatus("1");
            List<PermissionRequest> list = permissionRequestMapper.selectPermissionRequestList(query);
            if (list == null || list.isEmpty()) {
                permissionRequestMapper.updateUserRoleLevel(request.getUserId(), 2);
            } else {
                permissionRequestMapper.updateUserRoleLevel(request.getUserId(), 1);
            }
        }
    }

    @Transactional
    @Override
    public int rollbackExpiredApprovedRequests() {
        List<PermissionRequest> requests = permissionRequestMapper.selectExpiredApprovedRequests(SYSTEM_CODE);
        for (PermissionRequest request : requests) {
            rollback(request.getRequestId());
        }
        return requests.size();
    }

    @Override
    public boolean hasActivePermission(Long userId, String featureCode) {
        if (userId == null || featureCode == null || featureCode.trim().isEmpty()) {
            return false;
        }
        return permissionRequestMapper.selectLatestApprovedTemporaryRequest(userId, SYSTEM_CODE, featureCode.trim()) != null;
    }

    private void validateSubmit(PermissionRequest request) {
        if (request.getUserId() == null) {
            throw new IllegalArgumentException("缺少用户ID");
        }
        if (request.getOriginalLevel() == null) {
            throw new IllegalArgumentException("缺少原始权限等级");
        }
        if (request.getRequestLevel() == null || request.getRequestLevel() != 1) {
            throw new IllegalArgumentException("生成域仅允许申请查看公共密钥列表权限");
        }
        if (request.getRequestReason() == null || request.getRequestReason().trim().length() < 4) {
            throw new IllegalArgumentException("申请理由过短");
        }
    }

    private PermissionRequest requirePending(Long requestId) {
        PermissionRequest request = get(requestId);
        if (request == null) {
            throw new IllegalArgumentException("权限申请不存在");
        }
        if (!"0".equals(request.getStatus())) {
            throw new IllegalArgumentException("该申请已处理，无法重复审批");
        }
        return request;
    }

    private String blankToDefault(String value, String fallback) {
        return value == null || value.trim().isEmpty() ? fallback : value.trim();
    }

    private boolean isTemporaryRequest(PermissionRequest request) {
        return request != null && Integer.valueOf(1).equals(request.getIsTemp());
    }
}
