package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.common.TableDataInfo;
import com.ruoyi.updatedel.domain.PermissionRequest;
import com.ruoyi.updatedel.domain.SysUser;
import com.ruoyi.updatedel.repository.PermissionRequestRepository;
import com.ruoyi.updatedel.repository.SysUserRepository;
import java.util.Date;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PermissionRequestService {
    private final PermissionRequestRepository permissionRequestRepository;
    private final SysUserRepository sysUserRepository;

    public PermissionRequestService(PermissionRequestRepository permissionRequestRepository, SysUserRepository sysUserRepository) {
        this.permissionRequestRepository = permissionRequestRepository;
        this.sysUserRepository = sysUserRepository;
    }

    public TableDataInfo list(PermissionRequest query, int pageNum, int pageSize) {
        int validPage = Math.max(pageNum, 1);
        int validSize = Math.max(pageSize, 10);
        int offset = (validPage - 1) * validSize;
        return new TableDataInfo(permissionRequestRepository.findPage(query, offset, validSize), permissionRequestRepository.count(query));
    }

    public Optional<PermissionRequest> findById(Long requestId) {
        return permissionRequestRepository.findById(requestId);
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
        Long requestId = permissionRequestRepository.insert(request);
        return permissionRequestRepository.findById(requestId)
            .orElseThrow(() -> new IllegalStateException("权限申请保存失败"));
    }

    @Transactional
    public void approve(Long requestId, String approveBy, String approveNote) {
        PermissionRequest request = requirePendingRequest(requestId);
        permissionRequestRepository.markApproved(requestId, approveBy, approveNote);
        sysUserRepository.updateRoleLevel(request.getUserId(), request.getRequestLevel());
    }

    @Transactional
    public void reject(Long requestId, String approveBy, String approveNote) {
        requirePendingRequest(requestId);
        permissionRequestRepository.markRejected(requestId, approveBy, approveNote);
    }

    @Transactional
    public void rollback(Long requestId) {
        PermissionRequest request = permissionRequestRepository.findById(requestId)
            .orElseThrow(() -> new IllegalStateException("权限申请不存在"));
        if (!"1".equals(request.getStatus())) {
            throw new IllegalStateException("该申请未通过审批，无需回退");
        }
        sysUserRepository.updateRoleLevel(request.getUserId(), request.getOriginalLevel());
        permissionRequestRepository.markRolledBack(requestId);
    }

    public List<PermissionRequest> findExpiredApproved(Date expireBefore) {
        return permissionRequestRepository.findApprovedBefore(expireBefore);
    }

    private PermissionRequest requirePendingRequest(Long requestId) {
        PermissionRequest request = permissionRequestRepository.findById(requestId)
            .orElseThrow(() -> new IllegalStateException("权限申请不存在"));
        if (!"0".equals(request.getStatus())) {
            throw new IllegalStateException("该申请已处理，无法重复审批");
        }
        return request;
    }

    private SysUser loadUser(Long userId, String userName) {
        if (userId != null) {
            return sysUserRepository.findById(userId)
                .orElseThrow(() -> new IllegalStateException("用户不存在: " + userId));
        }
        if (userName != null && !userName.trim().isEmpty()) {
            return sysUserRepository.findByUserName(userName.trim())
                .orElseThrow(() -> new IllegalStateException("用户不存在: " + userName));
        }
        throw new IllegalStateException("提交权限申请时必须提供 userId 或 userName");
    }
}
