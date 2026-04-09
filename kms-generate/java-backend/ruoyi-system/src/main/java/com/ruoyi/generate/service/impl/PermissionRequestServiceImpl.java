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
        permissionRequestMapper.updateUserRoleLevel(request.getUserId(), request.getRequestLevel());
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
        permissionRequestMapper.updateUserRoleLevel(request.getUserId(), request.getOriginalLevel());
        request.setStatus("3");
        request.setRollbackTime(new Date());
        permissionRequestMapper.updatePermissionRequest(request);
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
}
