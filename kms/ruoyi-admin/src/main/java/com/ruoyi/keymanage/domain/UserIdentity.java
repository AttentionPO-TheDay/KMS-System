package com.ruoyi.keymanage.domain;

/**
 * 用户标识类
 * 目前只用到了identityData标识数据
 */
public class UserIdentity {
    private String version;
    private String identityType;
    private String alias;
    private String identityData;//标识数据
    private String serial;
    private String validSrart;
    private String validEnd;
    private String idExtensions;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getIdentityType() {
        return identityType;
    }

    public void setIdentityType(String identityType) {
        this.identityType = identityType;
    }

    public String getAlias() {
        return alias;
    }

    public void setAlias(String alias) {
        this.alias = alias;
    }

    public String getSerial() {
        return serial;
    }

    public void setSerial(String serial) {
        this.serial = serial;
    }

    public String getValidSrart() {
        return validSrart;
    }

    public void setValidSrart(String validSrart) {
        this.validSrart = validSrart;
    }

    public String getValidEnd() {
        return validEnd;
    }

    public void setValidEnd(String validEnd) {
        this.validEnd = validEnd;
    }

    public String getIdExtensions() {
        return idExtensions;
    }

    public void setIdExtensions(String idExtensions) {
        this.idExtensions = idExtensions;
    }

    public String getIdentityData() {
        return identityData;
    }

    public void setIdentityData(String identityData) {
        this.identityData = identityData;
    }

}