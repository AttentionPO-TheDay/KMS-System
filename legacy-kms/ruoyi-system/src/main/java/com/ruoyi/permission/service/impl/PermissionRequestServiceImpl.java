package com.ruoyi.permission.service.impl;

import java.util.Date;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.ruoyi.permission.mapper.PermissionRequestMapper;
import com.ruoyi.permission.domain.PermissionRequest;
import com.ruoyi.permission.service.IPermissionRequestService;
import com.ruoyi.system.service.ISysUserService;
import com.ruoyi.common.core.domain.entity.SysUser;

/**
 * 权限申请Service业务层处理
 * 
 * @author ruoyi
 * @date 2025-12-08
 */
@Service
public class PermissionRequestServiceImpl implements IPermissionRequestService {
    @Autowired
    private PermissionRequestMapper permissionRequestMapper;

    @Autowired
    private ISysUserService userService;

    /**
     * 查询权限申请
     * 
     * @param requestId 权限申请主键
     * @return 权限申请
     */
    @Override
    public PermissionRequest selectPermissionRequestByRequestId(Long requestId) {
        return permissionRequestMapper.selectPermissionRequestByRequestId(requestId);
    }

    /**
     * 查询权限申请列表
     * 
     * @param permissionRequest 权限申请
     * @return 权限申请
     */
    @Override
    public List<PermissionRequest> selectPermissionRequestList(PermissionRequest permissionRequest) {
        return permissionRequestMapper.selectPermissionRequestList(permissionRequest);
    }

    /**
     * 新增权限申请
     * 
     * @param permissionRequest 权限申请
     * @return 结果
     */
    @Override
    public int insertPermissionRequest(PermissionRequest permissionRequest) {
        // 设置申请时间
        permissionRequest.setRequestTime(new Date());
        // 默认状态为待审批
        permissionRequest.setStatus("0");
        // 默认为临时权限
        if (permissionRequest.getIsTemp() == null) {
            permissionRequest.setIsTemp(1);
        }
        return permissionRequestMapper.insertPermissionRequest(permissionRequest);
    }

    /**
     * 修改权限申请
     * 
     * @param permissionRequest 权限申请
     * @return 结果
     */
    @Override
    public int updatePermissionRequest(PermissionRequest permissionRequest) {
        return permissionRequestMapper.updatePermissionRequest(permissionRequest);
    }

    /**
     * 审批通过权限申请（临时提升用户权限）
     * 
     * @param requestId   申请ID
     * @param approveBy   审批人
     * @param approveNote 审批备注
     * @return 结果
     */
    @Override
    @Transactional
    public int approveRequest(Long requestId, String approveBy, String approveNote) {
        // 查询申请信息
        PermissionRequest request = permissionRequestMapper.selectPermissionRequestByRequestId(requestId);
        if (request == null) {
            throw new RuntimeException("权限申请不存在");
        }

        if (!"0".equals(request.getStatus())) {
            throw new RuntimeException("该申请已处理，无法重复审批");
        }

        // 更新申请状态为已通过
        request.setStatus("1");
        request.setApproveBy(approveBy);
        request.setApproveTime(new Date());
        request.setApproveNote(approveNote);

        int result = permissionRequestMapper.updatePermissionRequest(request);

        // 临时提升用户权限
        SysUser user = userService.selectUserById(request.getUserId());
        if (user != null) {
            user.setRoleLevel(request.getRequestLevel());
            userService.updateUser(user);
        }

        return result;
    }

    /**
     * 审批拒绝权限申请
     * 
     * @param requestId   申请ID
     * @param approveBy   审批人
     * @param approveNote 审批备注
     * @return 结果
     */
    @Override
    public int rejectRequest(Long requestId, String approveBy, String approveNote) {
        PermissionRequest request = permissionRequestMapper.selectPermissionRequestByRequestId(requestId);
        if (request == null) {
            throw new RuntimeException("权限申请不存在");
        }

        if (!"0".equals(request.getStatus())) {
            throw new RuntimeException("该申请已处理，无法重复审批");
        }

        // 更新申请状态为已拒绝
        request.setStatus("2");
        request.setApproveBy(approveBy);
        request.setApproveTime(new Date());
        request.setApproveNote(approveNote);

        return permissionRequestMapper.updatePermissionRequest(request);
    }

    /**
     * 回退用户权限到原始等级
     * 
     * @param requestId 申请ID
     * @return 结果
     */
    @Override
    @Transactional
    public int rollbackPermission(Long requestId) {
        System.out.println("[ROLLBACK] ========== 开始回退权限 ==========");
        System.out.println("[ROLLBACK] Request ID: " + requestId);

        // 查询申请信息
        PermissionRequest request = permissionRequestMapper.selectPermissionRequestByRequestId(requestId);
        if (request == null) {
            System.out.println("[ROLLBACK] 错误: 权限申请不存在");
            throw new RuntimeException("权限申请不存在");
        }

        System.out.println("[ROLLBACK] 找到申请记录 - 用户: " + request.getUserName() + ", 用户ID: " + request.getUserId());
        System.out.println("[ROLLBACK] 原始等级: " + request.getOriginalLevel() + ", 申请等级: " + request.getRequestLevel());
        System.out.println("[ROLLBACK] 当前状态: " + request.getStatus());

        if (!"1".equals(request.getStatus())) {
            System.out.println("[ROLLBACK] 错误: 该申请未通过审批，无需回退 (status=" + request.getStatus() + ")");
            throw new RuntimeException("该申请未通过审批，无需回退");
        }

        // 回退用户权限到原始等级
        SysUser user = userService.selectUserById(request.getUserId());
        if (user != null) {
            System.out.println("[ROLLBACK] 查询到用户 - 当前 role_level: " + user.getRoleLevel());
            System.out.println(
                    "[ROLLBACK] 准备更新 role_level 从 " + user.getRoleLevel() + " 到 " + request.getOriginalLevel());
            user.setRoleLevel(request.getOriginalLevel());
            int updateResult = userService.updateUser(user);
            System.out.println("[ROLLBACK] 用户更新结果: " + updateResult);
        } else {
            System.out.println("[ROLLBACK] 警告: 未找到用户ID=" + request.getUserId());
        }

        // 更新申请状态为已使用并回退
        request.setStatus("3");
        request.setRollbackTime(new Date());
        int result = permissionRequestMapper.updatePermissionRequest(request);

        System.out.println("[ROLLBACK] 申请状态更新结果: " + result);
        System.out.println("[ROLLBACK] ========== 回退完成 ==========");

        return result;
    }

    /**
     * 批量删除权限申请
     * 
     * @param requestIds 需要删除的权限申请主键
     * @return 结果
     */
    @Override
    public int deletePermissionRequestByRequestIds(Long[] requestIds) {
        return permissionRequestMapper.deletePermissionRequestByRequestIds(requestIds);
    }

    /**
     * 删除权限申请信息
     * 
     * @param requestId 权限申请主键
     * @return 结果
     */
    @Override
    public int deletePermissionRequestByRequestId(Long requestId) {
        return permissionRequestMapper.deletePermissionRequestByRequestId(requestId);
    }
}
