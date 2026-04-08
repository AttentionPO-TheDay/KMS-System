package com.ruoyi.permission.mapper;

import java.util.List;
import com.ruoyi.permission.domain.PermissionRequest;

/**
 * 权限申请Mapper接口
 * 
 * @author ruoyi
 * @date 2025-12-08
 */
public interface PermissionRequestMapper {
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
     * 新增权限申请
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
     * 删除权限申请
     * 
     * @param requestId 权限申请主键
     * @return 结果
     */
    public int deletePermissionRequestByRequestId(Long requestId);

    /**
     * 批量删除权限申请
     * 
     * @param requestIds 需要删除的数据主键集合
     * @return 结果
     */
    public int deletePermissionRequestByRequestIds(Long[] requestIds);
}
