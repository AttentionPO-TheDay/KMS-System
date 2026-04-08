package com.ruoyi.distribute.domain;

import java.io.Serializable;
import com.alibaba.fastjson2.annotation.JSONField;

public class Keymanage implements Serializable {
    private static final long serialVersionUID = 1L;

    private Long keyId;
    private Long userId;

    @JSONField(name = "user_name")
    private String userName;

    private UserIdentity userIdentity;

    @JSONField(name = "encryt_type")
    private String encrytType;

    @JSONField(name = "encryt_name")
    private String encrytName;

    @JSONField(name = "key_name")
    private String keyName;

    private String chainHash;
    private Long blockHeight;

    public Long getKeyId() {
        return keyId;
    }

    public void setKeyId(Long keyId) {
        this.keyId = keyId;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public String getUserName() {
        return userName;
    }

    public void setUserName(String userName) {
        this.userName = userName;
    }

    public UserIdentity getUserIdentity() {
        return userIdentity;
    }

    public void setUserIdentity(UserIdentity userIdentity) {
        this.userIdentity = userIdentity;
    }

    public String getEncrytType() {
        return encrytType;
    }

    public void setEncrytType(String encrytType) {
        this.encrytType = encrytType;
    }

    public String getEncrytName() {
        return encrytName;
    }

    public void setEncrytName(String encrytName) {
        this.encrytName = encrytName;
    }

    public String getKeyName() {
        return keyName;
    }

    public void setKeyName(String keyName) {
        this.keyName = keyName;
    }

    public String getChainHash() {
        return chainHash;
    }

    public void setChainHash(String chainHash) {
        this.chainHash = chainHash;
    }

    public Long getBlockHeight() {
        return blockHeight;
    }

    public void setBlockHeight(Long blockHeight) {
        this.blockHeight = blockHeight;
    }
}
