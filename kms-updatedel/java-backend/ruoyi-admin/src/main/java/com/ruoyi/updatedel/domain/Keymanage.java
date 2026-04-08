package com.ruoyi.updatedel.domain;

import lombok.Data;

@Data
public class Keymanage {
    private Long keyId;
    private Long userId;
    private String userName;
    private String ua;
    private String encrytType;
    private String encrytName;
    private String keyName;
    private String keyUse;
    private String keyValue;
    private String creTime;
    private String updTime;
    private String autoUpdate;
    private String status;
    private Integer version;
    private String chainHash;
    private Long blockHeight;
    private String chainStatus;
    private String keyDomain;
}
