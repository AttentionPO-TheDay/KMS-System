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
    private static final String SYSTEM_CODE = "lifecycle";
    private static final String FEATURE_CODE = "AUTO_UPDATE";
    private static final String FEATURE_NAME = "密钥自动更新";
    /** 本域唯一功能的目标等级：0 = 管理员级（即"可托管自动更新"），由服务端固定 */
    private static final Integer REQUEST_LEVEL = 0;

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
        request.setSystemCode(SYSTEM_CODE);
        request.setFeatureCode(FEATURE_CODE);
        request.setFeatureName(FEATURE_NAME);
        // requestLevel 必须由服务端定，不能依赖客户端传：
        // 本域只有 AUTO_UPDATE 一个功能，其目标等级固定为 0。
        // 原先不设置它会直接把 NULL 写进 NOT NULL 的 request_level 列，
        // 结果是调用方漏传一个字段就得到一句笼统的"系统内部错误"。
        request.setRequestLevel(REQUEST_LEVEL);
        request.setOriginalLevel(user.getRoleLevel() == 1 ? 2 : user.getRoleLevel());
        request.setStatus("0");
        request.setIsTemp(request.getIsTemp() == null ? 1 : request.getIsTemp());
        request.setRequestTime(new Date());
        permissionRequestMapper.insertPermissionRequest(request);
        return Optional.ofNullable(permissionRequestMapper.selectPermissionRequestById(request.getRequestId()))
            .orElseThrow(() -> new IllegalStateException("权限申请保存失败"));
    }

    @Transactional
    public void approve(Long requestId, String approveBy, String approveNote) {
        requirePendingRequest(requestId);
        permissionRequestMapper.markApproved(requestId, approveBy, approveNote);
        // 刻意**不**调用 sysUserMapper.updateRoleLevel(...)。
        //
        // 原先这里会把申请人的 role_level 改成 requestLevel（本域固定为 0），
        // 于是「临时拿到自动更新权限」被实现成了「临时变成管理员」。这在 D9 之后是硬伤：
        // 登录分流判据正是 role_level <= 0，用户下次登录会被直接送进管理控制台。
        //
        // 临时授权本来就不需要改 role_level —— 放行由
        // LifecycleKeyController 的 hasActiveTemporaryPermission(userId) 判定，
        // 用户前台则由 permission_request 里 status=1 且 is_temp=1 的记录判定。
        // 因此 role_level 现在是一个**纯静态的账号属性**（见计划 §3.4 / D13）。
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
        permissionRequestMapper.markRolledBack(requestId);
        // 同样刻意不动 role_level。原来的实现会在回退时把用户写成 2，或在"还有其它已通过申请"
        // 时写成 **1** —— 而等级 1（中级用户）已随 D1 废弃，写 1 等于凭空造出一个非法等级。
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
            rollback(request.getRequestId());
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

    public boolean hasActiveTemporaryPermission(Long userId) {
        return userId != null && permissionRequestMapper.selectLatestApprovedTemporaryRequest(userId) != null;
    }
}
