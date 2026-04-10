package com.ruoyi.generate.mapper;

import com.ruoyi.generate.domain.PermissionRequest;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface PermissionRequestMapper {
    PermissionRequest selectPermissionRequestByRequestId(Long requestId);

    int deletePermissionRequestByRequestId(Long requestId);

    List<PermissionRequest> selectPermissionRequestList(PermissionRequest permissionRequest);

    int insertPermissionRequest(PermissionRequest permissionRequest);

    int updatePermissionRequest(PermissionRequest permissionRequest);

    List<PermissionRequest> selectExpiredApprovedRequests(@Param("systemCode") String systemCode);

    PermissionRequest selectLatestApprovedTemporaryRequest(@Param("userId") Long userId,
                                                           @Param("systemCode") String systemCode,
                                                           @Param("featureCode") String featureCode);

    int updateUserRoleLevel(@Param("userId") Long userId, @Param("roleLevel") Integer roleLevel);
}
