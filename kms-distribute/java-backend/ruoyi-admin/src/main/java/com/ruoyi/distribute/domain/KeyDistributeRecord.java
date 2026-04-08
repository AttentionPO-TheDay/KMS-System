package com.ruoyi.distribute.domain;

import java.util.Date;
import com.alibaba.fastjson2.annotation.JSONField;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.ruoyi.common.annotation.Excel;
import com.ruoyi.common.core.domain.BaseEntity;

/**
 * 密钥分发记录对象 key_distribute_record
 */
public class KeyDistributeRecord extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    /** 记录ID */
    @Excel(name = "记录ID", cellType = Excel.ColumnType.NUMERIC)
    private Long recordId;

    /** 密钥ID */
    @JSONField(name = "key_id")
    @Excel(name = "密钥ID", cellType = Excel.ColumnType.NUMERIC)
    private Long keyId;

    /** 用户ID */
    @JSONField(name = "user_id")
    private Long userId;

    /** 用户名 */
    @JSONField(name = "user_name")
    @Excel(name = "用户名")
    private String userName;

    /** 密钥名称 */
    @JSONField(name = "key_name")
    @Excel(name = "密钥名称")
    private String keyName;

    /** 加密算法类型 */
    @JSONField(name = "encryt_type")
    private String encrytType;

    /** 加密算法名称 */
    @JSONField(name = "encryt_name")
    @Excel(name = "加密算法")
    private String encrytName;

    /** 分发类型 */
    @JSONField(name = "distribute_type")
    @Excel(name = "分发类型", readConverterExp = "1=初始分发,2=更新分发,3=回收后补发")
    private String distributeType;

    /** 分发状态 */
    @JSONField(name = "distribute_status")
    @Excel(name = "分发状态", readConverterExp = "0=待分发,1=分发中,2=分发成功,3=分发失败")
    private String distributeStatus;

    /** 分发时间 */
    @JSONField(name = "distribute_time")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "分发时间", width = 30, dateFormat = "yyyy-MM-dd HH:mm:ss")
    private Date distributeTime;

    /** 区块链交易Hash */
    @JSONField(name = "chain_hash")
    @Excel(name = "区块链Hash", width = 40)
    private String chainHash;

    /** 区块高度 */
    @JSONField(name = "block_height")
    @Excel(name = "区块高度")
    private Long blockHeight;

    public Long getRecordId()
    {
        return recordId;
    }

    public void setRecordId(Long recordId)
    {
        this.recordId = recordId;
    }

    public Long getKeyId()
    {
        return keyId;
    }

    public void setKeyId(Long keyId)
    {
        this.keyId = keyId;
    }

    public Long getUserId()
    {
        return userId;
    }

    public void setUserId(Long userId)
    {
        this.userId = userId;
    }

    public String getUserName()
    {
        return userName;
    }

    public void setUserName(String userName)
    {
        this.userName = userName;
    }

    public String getKeyName()
    {
        return keyName;
    }

    public void setKeyName(String keyName)
    {
        this.keyName = keyName;
    }

    public String getEncrytType()
    {
        return encrytType;
    }

    public void setEncrytType(String encrytType)
    {
        this.encrytType = encrytType;
    }

    public String getEncrytName()
    {
        return encrytName;
    }

    public void setEncrytName(String encrytName)
    {
        this.encrytName = encrytName;
    }

    public String getDistributeType()
    {
        return distributeType;
    }

    public void setDistributeType(String distributeType)
    {
        this.distributeType = distributeType;
    }

    public String getDistributeStatus()
    {
        return distributeStatus;
    }

    public void setDistributeStatus(String distributeStatus)
    {
        this.distributeStatus = distributeStatus;
    }

    public Date getDistributeTime()
    {
        return distributeTime;
    }

    public void setDistributeTime(Date distributeTime)
    {
        this.distributeTime = distributeTime;
    }

    public String getChainHash()
    {
        return chainHash;
    }

    public void setChainHash(String chainHash)
    {
        this.chainHash = chainHash;
    }

    public Long getBlockHeight()
    {
        return blockHeight;
    }

    public void setBlockHeight(Long blockHeight)
    {
        this.blockHeight = blockHeight;
    }
}
