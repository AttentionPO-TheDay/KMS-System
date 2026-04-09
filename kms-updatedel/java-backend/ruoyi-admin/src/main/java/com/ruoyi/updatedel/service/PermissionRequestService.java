package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.PermissionRequest;
import com.ruoyi.updatedel.domain.SysUser;
import com.ruoyi.updatedel.mapper.PermissionRequestMapper;
import com.ruoyi.updatedel.mapper.SysUserMapper;
import java.util.Date;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PermissionRequestService {
    private final PermissionRequestMapper permissionRequestMapper;
    private final SysUserMapper sysUserMapper;

    public PermissionRequestService(PermissionRequestMapper permissionRequestMapper, SysUserMapper sysUserMapper) {
        this.permissionRequestMapper = permissionRequestMapper;
        this.sysUserMapper = sysUserMapper;
    }

    public List<PermissionRequest> list(PermissionRequest query) {
        return permissionRequestMapper.selectPermissionRequestList(query);
    }

    public Optional<PermissionRequest> findById(Long requestId) {
        return Optional.ofNullable(permissionRequestMapper.selectPermissionRequestById(requestId));
    }

    @Transactional
    public void delete(Long requestId) {
        PermissionRequest request = findById(requestId)
            .orElseThrow(() -> new IllegalStateException("权限申请不存在"));
        if ("1".equals(request.getStatus())) {
            throw new IllegalStateException("已审批通过的申请不能直接删除，请先回退");
        }
        permissionRequestMapper.deletePermissionRequestById(requestId);
    }

    @Transactional
    public PermissionRequest submit(PermissionRequest request) {
        SysUser user = loadUser(request.getUserId(), request.getUserName());
        request.setUserId(user.getUserId());
        request.setUserName(user.getUserName());
        request.setOriginalLevel(user.getRoleLevel());
        request.setStatus("0");
        request.setIsTemp(request.getIsTemp() == null ? 1 : request.getIsTemp());
        request.setRequestTime(new Date());
        permissionRequestMapper.insertPermissionRequest(request);
        return Optional.ofNullable(permissionRequestMapper.selectPermissionRequestById(request.getRequestId()))
            .orElseThrow(() -> new IllegalStateException("权限申请保存失败"));
    }

    @Transactional
    public void approve(Long requestId, String approveBy, String approveNote) {
        PermissionRequest request = requirePendingRequest(requestId);
        permissionRequestMapper.markApproved(requestId, approveBy, approveNote);
        sysUserMapper.updateRoleLevel(request.getUserId(), request.getRequestLevel());
    }

    @Transactional
    public void reject(Long requestId, String approveBy, String approveNote) {
        requirePendingRequest(requestId);
        permissionRequestMapper.markRejected(requestId, approveBy, approveNote);
    }

    @Transactional
    public void rollback(Long requestId) {
        PermissionRequest request = findById(requestId)
            .orElseThrow(() -> new IllegalStateException("权限申请不存在"));
        if (!"1".equals(request.getStatus())) {
            throw new IllegalStateException("该申请未通过审批，无需回退");
        }
        sysUserMapper.updateRoleLevel(request.getUserId(), request.getOriginalLevel());
        permissionRequestMapper.markRolledBack(requestId);
    }

    public List<PermissionRequest> findExpiredApproved(Date expireBefore) {
        return permissionRequestMapper.selectApprovedBefore(expireBefore);
    }

    @Transactional
    public int rollbackExpiredApprovedRequests() {
        Date expireBefore = new Date(System.currentTimeMillis() - TimeUnit.MINUTES.toMillis(30));
        List<PermissionRequest> expiredRequests = permissionRequestMapper.selectApprovedBefore(expireBefore);
        int rollbackCount = 0;

        for (PermissionRequest request : expiredRequests) {
            sysUserMapper.updateRoleLevel(request.getUserId(), request.getOriginalLevel());
            permissionRequestMapper.markRolledBack(request.getRequestId());
            rollbackCount++;
        }

        return rollbackCount;
    }

    private PermissionRequest requirePendingRequest(Long requestId) {
        PermissionRequest request = findById(requestId)
            .orElseThrow(() -> new IllegalStateException("权限申请不存在"));
        if (!"0".equals(request.getStatus())) {
            throw new IllegalStateException("该申请已处理，无法重复审批");
        }
        return request;
    }

    private SysUser loadUser(Long userId, String userName) {
        if (userId != null) {
            return Optional.ofNullable(sysUserMapper.selectUserById(userId))
                .orElseThrow(() -> new IllegalStateException("用户不存在: " + userId));
        }
        if (userName != null && !userName.trim().isEmpty()) {
            return Optional.ofNullable(sysUserMapper.selectUserByUserName(userName.trim()))
                .orElseThrow(() -> new IllegalStateException("用户不存在: " + userName));
        }
        throw new IllegalStateException("提交权限申请时必须提供 userId 或 userName");
    }
}
