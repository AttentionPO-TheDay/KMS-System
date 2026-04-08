package com.ruoyi.distribute.domain;

import com.alibaba.fastjson2.annotation.JSONField;
import java.io.Serializable;

/**
 * 密钥分发记录对象 key_distribute_record
 */
public class KeyDistributeRecord implements Serializable {
    private static final long serialVersionUID = 1L;

    /** 记录ID */
    private Long recordId;

    /** 密钥ID */
    @JSONField(name = "key_id")
    private Long keyId;

    /** 用户ID */
    @JSONField(name = "user_id")
    private Long userId;

    /** 用户名 */
    @JSONField(name = "user_name")
    private String userName;

    /** 密钥名称 */
    @JSONField(name = "key_name")
    private String keyName;

    /** 加密算法类型 */
    @JSONField(name = "encryt_type")
    private String encrytType;

    /** 加密算法名称 */
    @JSONField(name = "encryt_name")
    private String encrytName;

    /** 分发类型 (1=初始分发, 2=更新分发, 3=回收后补发) */
    @JSONField(name = "distribute_type")
    private String distributeType;

    /** 分发状态 (0=待分发, 1=分发中, 2=分发成功, 3=分发失败) */
    @JSONField(name = "distribute_status")
    private String distributeStatus;

    /** 分发时间 */
    @JSONField(name = "distribute_time")
    private String distributeTime;

    /** 区块链交易Hash */
    @JSONField(name = "chain_hash")
    private String chainHash;

    /** 区块高度 */
    @JSONField(name = "block_height")
    private Long blockHeight;

    /** 备注 */
    @JSONField(name = "remark")
    private String remark;

    /** 创建时间 */
    @JSONField(name = "cre_time")
    private String creTime;

    /** 更新时间 */
    @JSONField(name = "upd_time")
    private String updTime;

    public Long getRecordId() { return recordId; }
    public void setRecordId(Long recordId) { this.recordId = recordId; }

    public Long getKeyId() { return keyId; }
    public void setKeyId(Long keyId) { this.keyId = keyId; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getUserName() { return userName; }
    public void setUserName(String userName) { this.userName = userName; }

    public String getKeyName() { return keyName; }
    public void setKeyName(String keyName) { this.keyName = keyName; }

    public String getEncrytType() { return encrytType; }
    public void setEncrytType(String encrytType) { this.encrytType = encrytType; }

    public String getEncrytName() { return encrytName; }
    public void setEncrytName(String encrytName) { this.encrytName = encrytName; }

    public String getDistributeType() { return distributeType; }
    public void setDistributeType(String distributeType) { this.distributeType = distributeType; }

    public String getDistributeStatus() { return distributeStatus; }
    public void setDistributeStatus(String distributeStatus) { this.distributeStatus = distributeStatus; }

    public String getDistributeTime() { return distributeTime; }
    public void setDistributeTime(String distributeTime) { this.distributeTime = distributeTime; }

    public String getChainHash() { return chainHash; }
    public void setChainHash(String chainHash) { this.chainHash = chainHash; }

    public Long getBlockHeight() { return blockHeight; }
    public void setBlockHeight(Long blockHeight) { this.blockHeight = blockHeight; }

    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }

    public String getCreTime() { return creTime; }
    public void setCreTime(String creTime) { this.creTime = creTime; }

    public String getUpdTime() { return updTime; }
    public void setUpdTime(String updTime) { this.updTime = updTime; }
}
