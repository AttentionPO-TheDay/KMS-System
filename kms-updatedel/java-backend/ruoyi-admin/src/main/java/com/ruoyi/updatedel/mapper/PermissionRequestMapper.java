package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.PermissionRequest;
import java.util.Date;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface PermissionRequestMapper {
    PermissionRequest selectPermissionRequestById(Long requestId);

    List<PermissionRequest> selectPermissionRequestList(PermissionRequest query);

    List<PermissionRequest> selectApprovedBefore(Date beforeTime);

    int insertPermissionRequest(PermissionRequest request);

    int deletePermissionRequestById(Long requestId);

    int markApproved(@Param("requestId") Long requestId, @Param("approveBy") String approveBy,
                     @Param("approveNote") String approveNote);

    int markRejected(@Param("requestId") Long requestId, @Param("approveBy") String approveBy,
                     @Param("approveNote") String approveNote);

    int markRolledBack(Long requestId);
}
