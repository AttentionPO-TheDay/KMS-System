package com.ruoyi.generate.domain;

import com.alibaba.fastjson2.annotation.JSONField;
import java.io.Serializable;

/**
 * 密钥管理对象 keymanage
 * @date 2025-01-14
 */
public class Keymanage implements Serializable {
    private static final long serialVersionUID = 1L;

    /** 密钥ID */
    @JSONField(name = "key_id")
    private Long keyId;

    /** 用户ID */
    @JSONField(name = "user_id")
    private Long userId;

    /** 用户名 */
    @JSONField(name = "user_name")
    private String userName;

    /** 用户标识 */
    private UserIdentity userIdentity;

    /** 用户的部分公钥 */
    @JSONField(name = "ua")
    private String uA;

    /** 加密算法类型 */
    @JSONField(name = "encryt_type")
    private String encrytType;

    /** 加密算法名称 */
    @JSONField(name = "encryt_name")
    private String encrytName;

    /** 密钥名称 */
    @JSONField(name = "key_name")
    private String keyName;

    /** 密钥用途 */
    @JSONField(name = "key_use")
    private String keyUse;

    /** 密钥值 */
    @JSONField(name = "key_value")
    private String keyValue;

    /** 创建时间 */
    @JSONField(name = "cre_time")
    private String creTime;

    /** 更新时间 */
    @JSONField(name = "upd_time")
    private String updTime;

    /** 密钥自动更新状态 */
    @JSONField(name = "auto_update")
    private String autoUpdate;

    /** 密钥工作状态 */
    @JSONField(name = "status")
    private String status;

    /** SSCL密钥的域 */
    @JSONField(name = "key_domain")
    private String keyDomain;

    /** 密钥版本号 */
    @JSONField(name = "version")
    private Integer version;

    /** 区块链交易Hash */
    @JSONField(name = "chain_hash")
    private String chainHash;

    /** 区块高度 */
    @JSONField(name = "block_height")
    private Long blockHeight;

    /** 上链状态 (0=待上链, 1=已上链, 2=失败) */
    @JSONField(name = "chain_status")
    private String chainStatus;

    public Long getKeyId() { return keyId; }
    public void setKeyId(Long keyId) { this.keyId = keyId; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getUserName() { return userName; }
    public void setUserName(String userName) { this.userName = userName; }

    public UserIdentity getUserIdentity() { return userIdentity; }
    public void setUserIdentity(UserIdentity userIdentity) { this.userIdentity = userIdentity; }

    public String getuA() { return uA; }
    public void setuA(String uA) { this.uA = uA; }

    public String getEncrytType() { return encrytType; }
    public void setEncrytType(String encrytType) { this.encrytType = encrytType; }

    public String getEncrytName() { return encrytName; }
    public void setEncrytName(String encrytName) { this.encrytName = encrytName; }

    public String getKeyName() { return keyName; }
    public void setKeyName(String keyName) { this.keyName = keyName; }

    public String getKeyUse() { return keyUse; }
    public void setKeyUse(String keyUse) { this.keyUse = keyUse; }

    public String getKeyValue() { return keyValue; }
    public void setKeyValue(String keyValue) { this.keyValue = keyValue; }

    public String getCreTime() { return creTime; }
    public void setCreTime(String creTime) { this.creTime = creTime; }

    public String getUpdTime() { return updTime; }
    public void setUpdTime(String updTime) { this.updTime = updTime; }

    public String getAutoUpdate() { return autoUpdate; }
    public void setAutoUpdate(String autoUpdate) { this.autoUpdate = autoUpdate; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getKeyDomain() { return keyDomain; }
    public void setKeyDomain(String keyDomain) { this.keyDomain = keyDomain; }

    public Integer getVersion() { return version; }
    public void setVersion(Integer version) { this.version = version; }

    public String getChainHash() { return chainHash; }
    public void setChainHash(String chainHash) { this.chainHash = chainHash; }

    public Long getBlockHeight() { return blockHeight; }
    public void setBlockHeight(Long blockHeight) { this.blockHeight = blockHeight; }

    public String getChainStatus() { return chainStatus; }
    public void setChainStatus(String chainStatus) { this.chainStatus = chainStatus; }

    @Override
    public String toString() {
        return "Keymanage{" +
                "keyId=" + keyId +
                ", userId=" + userId +
                ", userName='" + userName + '\'' +
                ", encrytType='" + encrytType + '\'' +
                ", encrytName='" + encrytName + '\'' +
                ", keyName='" + keyName + '\'' +
                ", status='" + status + '\'' +
                ", chainStatus='" + chainStatus + '\'' +
                ", version=" + version +
                '}';
    }
}
