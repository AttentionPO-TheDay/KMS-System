package com.ruoyi.updatedel.domain;

import java.util.Date;
import lombok.Data;

@Data
public class PermissionRequest {
    private Long requestId;
    private Long userId;
    private String userName;
    private Integer originalLevel;
    private Integer requestLevel;
    private String requestReason;
    private String status;
    private Integer isTemp;
    private Date requestTime;
    private String approveBy;
    private Date approveTime;
    private String approveNote;
    private Date useTime;
    private Date rollbackTime;
    private Date createTime;
    private Date updateTime;
}
