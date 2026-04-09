package com.ruoyi.updatedel.domain;

import java.util.Date;
import lombok.Data;

@Data
public class KeyOperationRecord {
    private Long recordId;
    private Long keyId;
    private Long userId;
    private String userName;
    private String keyName;
    private String encrytType;
    private String encrytName;
    private Integer keyVersion;
    private String actionType;
    private String actionSource;
    private String resultStatus;
    private String chainStatus;
    private String chainHash;
    private Long blockHeight;
    private String resultMessage;
    private String receiveStatus;
    private Date actionTime;
    private Date receiveTime;
    private Date createTime;
    private Date updateTime;
}
