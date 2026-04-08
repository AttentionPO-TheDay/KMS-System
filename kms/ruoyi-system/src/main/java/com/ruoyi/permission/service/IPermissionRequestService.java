package com.ruoyi.permission.service;

import java.util.List;
import com.ruoyi.permission.domain.PermissionRequest;

/**
 * 权限申请Service接口
 * 
 * @author ruoyi
 * @date 2025-12-08
 */
public interface IPermissionRequestService {
    /**
     * 查询权限申请
     * 
     * @param requestId 权限申请主键
     * @return 权限申请
     */
    public PermissionRequest selectPermissionRequestByRequestId(Long requestId);

    /**
     * 查询权限申请列表
     * 
     * @param permissionRequest 权限申请
     * @return 权限申请集合
     */
    public List<PermissionRequest> selectPermissionRequestList(PermissionRequest permissionRequest);

    /**
     * 新增权限申请（用户提交申请）
     * 
     * @param permissionRequest 权限申请
     * @return 结果
     */
    public int insertPermissionRequest(PermissionRequest permissionRequest);

    /**
     * 修改权限申请
     * 
     * @param permissionRequest 权限申请
     * @return 结果
     */
    public int updatePermissionRequest(PermissionRequest permissionRequest);

    /**
     * 审批通过权限申请（临时提升用户权限）
     * 
     * @param requestId   申请ID
     * @param approveBy   审批人
     * @param approveNote 审批备注
     * @return 结果
     */
    public int approveRequest(Long requestId, String approveBy, String approveNote);

    /**
     * 审批拒绝权限申请
     * 
     * @param requestId   申请ID
     * @param approveBy   审批人
     * @param approveNote 审批备注
     * @return 结果
     */
    public int rejectRequest(Long requestId, String approveBy, String approveNote);

    /**
     * 回退用户权限到原始等级
     * 
     * @param requestId 申请ID
     * @return 结果
     */
    public int rollbackPermission(Long requestId);

    /**
     * 批量删除权限申请
     * 
     * @param requestIds 需要删除的权限申请主键集合
     * @return 结果
     */
    public int deletePermissionRequestByRequestIds(Long[] requestIds);

    /**
     * 删除权限申请信息
     * 
     * @param requestId 权限申请主键
     * @return 结果
     */
    public int deletePermissionRequestByRequestId(Long requestId);
}
