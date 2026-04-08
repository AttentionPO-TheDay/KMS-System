package com.ruoyi.keymanage.domain;

import org.apache.commons.lang3.builder.ToStringBuilder;
import org.apache.commons.lang3.builder.ToStringStyle;
import com.ruoyi.common.annotation.Excel;
import com.ruoyi.common.core.domain.BaseEntity;
import com.alibaba.fastjson2.annotation.JSONField;
import org.bouncycastle.math.ec.ECPoint;

/**
 * 密钥管理对象 keymanage
 * @date 2025-01-14
 */
public class Keymanage extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 密钥ID */
    private Long keyId;

    /** 用户ID */
    @Excel(name = "用户ID")
    private Long userId;

    /** 用户名 */
    @Excel(name = "用户名")
    @JSONField(name = "user_name")
    private String userName;

    /** 用户标识 */
    private UserIdentity userIdentity;

    /** 用户的部分公钥 */
    @JSONField(name = "ua")
    private String uA;

    /** 加密算法类型 */
    @Excel(name = "加密算法类型")
    @JSONField(name = "encryt_type")
    private String encrytType;

    /** 加密算法名称 */
    @Excel(name = "加密算法名称")
    @JSONField(name = "encryt_name")
    private String encrytName;

    /** 密钥名称 */
    @Excel(name = "密钥名称")
    @JSONField(name = "key_name")
    private String keyName;

    /** 密钥用途 */
    @Excel(name = "密钥用途")
    @JSONField(name = "key_use")
    private String keyUse;

    /** 密钥值 */
    @Excel(name = "密钥值")
    @JSONField(name = "key_value")
    private String keyValue;

    /** 创建时间 */
    @Excel(name = "创建时间")
    @JSONField(name = "cre_time")
    private String creTime;

    /** 更新时间 */
    @Excel(name = "更新时间")
    @JSONField(name = "upd_time")
    private String updTime;

    /** 密钥自动更新状态 */
    @Excel(name = "密钥自动更新状态")
    @JSONField(name = "auto_update")
    private String autoUpdate;

    /** 密钥工作状态 */
    @Excel(name = "密钥工作状态")
    @JSONField(name = "status")
    private String status;

    /** SSCL密钥的域 */
    @JSONField(name = "key_domain")
    private String keyDomain;

    /** 密钥版本号  */
    @Excel(name = "版本号")
    private Integer version;

    /** 区块链交易Hash */
    @Excel(name = "区块链交易Hash")
    private String chainHash;

    /** 区块高度 */
    @Excel(name = "区块高度")
    private Long blockHeight;

    /** 上链状态 (0=待上链, 1=已上链, 2=失败) */
    @Excel(name = "上链状态", readConverterExp = "0=待上链,1=已上链,2=失败")
    private String chainStatus;


    public String getKeyDomain() {
        return keyDomain;
    }

    public void setKeyDomain(String keyDomain) {
        this.keyDomain = keyDomain;
    }

    public void setKeyId(Long keyId)
    {
        this.keyId = keyId;
    }

    public Long getKeyId()
    {
        return keyId;
    }
    public void setUserId(Long userId)
    {
        this.userId = userId;
    }

    public Long getUserId()
    {
        return userId;
    }
    public void setUserName(String userName)
    {
        this.userName = userName;
    }

    public String getUserName()
    {
        return userName;
    }
    public void setEncrytType(String encrytType)
    {
        this.encrytType = encrytType;
    }

    public String getEncrytType()
    {
        return encrytType;
    }
    public void setEncrytName(String encrytName)
    {
        this.encrytName = encrytName;
    }

    public String getEncrytName()
    {
        return encrytName;
    }
    public void setKeyName(String keyName)
    {
        this.keyName = keyName;
    }

    public String getKeyName()
    {
        return keyName;
    }
    public void setKeyUse(String keyUse)
    {
        this.keyUse = keyUse;
    }

    public String getKeyUse()
    {
        return keyUse;
    }
    public void setKeyValue(String keyValue)
    {
        this.keyValue = keyValue;
    }

    public String getKeyValue()
    {
        return keyValue;
    }
    public void setCreTime(String creTime)
    {
        this.creTime = creTime;
    }

    public String getCreTime()
    {
        return creTime;
    }
    public void setUpdTime(String updTime)
    {
        this.updTime = updTime;
    }

    public String getUpdTime()
    {
        return updTime;
    }
    public void setAutoUpdate(String autoUpdate)
    {
        this.autoUpdate = autoUpdate;
    }

    public String getAutoUpdate()
    {
        return autoUpdate;
    }
    public void setStatus(String status)
    {
        this.status = status;
    }

    public String getStatus()
    {
        return status;
    }

    public UserIdentity getUserIdentity() {
        return userIdentity;
    }

    public void setUserIdentity(UserIdentity userIdentity) {
        this.userIdentity = userIdentity;
    }

    public String getuA() {
        return uA;
    }

    public void setuA(String uA) {
        this.uA = uA;
    }


    public void setVersion(Integer version)
    {
        this.version = version;
    }

    public Integer getVersion()
    {
        return version;
    }

    public void setChainHash(String chainHash)
    {
        this.chainHash = chainHash;
    }

    public String getChainHash()
    {
        return chainHash;
    }

    public void setBlockHeight(Long blockHeight)
    {
        this.blockHeight = blockHeight;
    }

    public Long getBlockHeight()
    {
        return blockHeight;
    }

    public void setChainStatus(String chainStatus)
    {
        this.chainStatus = chainStatus;
    }

    public String getChainStatus()
    {
        return chainStatus;
    }

    @Override
    public String toString() {
        return new ToStringBuilder(this,ToStringStyle.MULTI_LINE_STYLE)
            .append("keyId", getKeyId())
            .append("userId", getUserId())
            .append("userName", getUserName())
            .append("encrytType", getEncrytType())
            .append("encrytName", getEncrytName())
            .append("keyName", getKeyName())
            .append("keyUse", getKeyUse())
            .append("keyValue", getKeyValue())
            .append("creTime", getCreTime())
            .append("updTime", getUpdTime())
            .append("autoUpdate", getAutoUpdate())
            .append("status", getStatus())
            .append("version", getVersion())
            .append("chainHash", getChainHash())
            .append("blockHeight", getBlockHeight())
            .append("chainStatus", getChainStatus())
            .toString();
    }
}