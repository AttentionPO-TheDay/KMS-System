package com.ruoyi.permission.domain;

import java.util.Date;
import com.fasterxml.jackson.annotation.JsonFormat;
import org.apache.commons.lang3.builder.ToStringBuilder;
import org.apache.commons.lang3.builder.ToStringStyle;
import com.ruoyi.common.annotation.Excel;
import com.ruoyi.common.core.domain.BaseEntity;

/**
 * 权限申请对象 permission_request
 * 
 * @author ruoyi
 * @date 2025-12-08
 */
public class PermissionRequest extends BaseEntity {
    private static final long serialVersionUID = 1L;

    /** 申请ID */
    private Long requestId;

    /** 申请用户ID */
    @Excel(name = "申请用户ID")
    private Long userId;

    /** 申请用户名 */
    @Excel(name = "申请用户名")
    private String userName;

    /** 原始权限等级 */
    @Excel(name = "原始权限等级")
    private Integer originalLevel;

    /** 申请的权限等级 */
    @Excel(name = "申请的权限等级", readConverterExp = "0=管理员,1=中级用户")
    private Integer requestLevel;

    /** 申请理由 */
    @Excel(name = "申请理由")
    private String requestReason;

    /** 申请状态 */
    @Excel(name = "申请状态", readConverterExp = "0=待审批,1=已通过,2=已拒绝,3=已使用并回退")
    private String status;

    /** 是否临时权限 */
    @Excel(name = "是否临时权限", readConverterExp = "1=是,0=否")
    private Integer isTemp;

    /** 申请时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "申请时间", width = 30, dateFormat = "yyyy-MM-dd HH:mm:ss")
    private Date requestTime;

    /** 审批人 */
    @Excel(name = "审批人")
    private String approveBy;

    /** 审批时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "审批时间", width = 30, dateFormat = "yyyy-MM-dd HH:mm:ss")
    private Date approveTime;

    /** 审批备注 */
    @Excel(name = "审批备注")
    private String approveNote;

    /** 权限使用时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private Date useTime;

    /** 权限回退时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private Date rollbackTime;

    public void setRequestId(Long requestId) {
        this.requestId = requestId;
    }

    public Long getRequestId() {
        return requestId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserName(String userName) {
        this.userName = userName;
    }

    public String getUserName() {
        return userName;
    }

    public void setOriginalLevel(Integer originalLevel) {
        this.originalLevel = originalLevel;
    }

    public Integer getOriginalLevel() {
        return originalLevel;
    }

    public void setRequestLevel(Integer requestLevel) {
        this.requestLevel = requestLevel;
    }

    public Integer getRequestLevel() {
        return requestLevel;
    }

    public void setRequestReason(String requestReason) {
        this.requestReason = requestReason;
    }

    public String getRequestReason() {
        return requestReason;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }

    public void setIsTemp(Integer isTemp) {
        this.isTemp = isTemp;
    }

    public Integer getIsTemp() {
        return isTemp;
    }

    public void setRequestTime(Date requestTime) {
        this.requestTime = requestTime;
    }

    public Date getRequestTime() {
        return requestTime;
    }

    public void setApproveBy(String approveBy) {
        this.approveBy = approveBy;
    }

    public String getApproveBy() {
        return approveBy;
    }

    public void setApproveTime(Date approveTime) {
        this.approveTime = approveTime;
    }

    public Date getApproveTime() {
        return approveTime;
    }

    public void setApproveNote(String approveNote) {
        this.approveNote = approveNote;
    }

    public String getApproveNote() {
        return approveNote;
    }

    public void setUseTime(Date useTime) {
        this.useTime = useTime;
    }

    public Date getUseTime() {
        return useTime;
    }

    public void setRollbackTime(Date rollbackTime) {
        this.rollbackTime = rollbackTime;
    }

    public Date getRollbackTime() {
        return rollbackTime;
    }

    @Override
    public String toString() {
        return new ToStringBuilder(this, ToStringStyle.MULTI_LINE_STYLE)
                .append("requestId", getRequestId())
                .append("userId", getUserId())
                .append("userName", getUserName())
                .append("originalLevel", getOriginalLevel())
                .append("requestLevel", getRequestLevel())
                .append("requestReason", getRequestReason())
                .append("status", getStatus())
                .append("isTemp", getIsTemp())
                .append("requestTime", getRequestTime())
                .append("approveBy", getApproveBy())
                .append("approveTime", getApproveTime())
                .append("approveNote", getApproveNote())
                .append("useTime", getUseTime())
                .append("rollbackTime", getRollbackTime())
                .append("createTime", getCreateTime())
                .append("updateTime", getUpdateTime())
                .toString();
    }
}
