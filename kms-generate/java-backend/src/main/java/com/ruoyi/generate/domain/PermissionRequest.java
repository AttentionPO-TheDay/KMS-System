package com.ruoyi.generate.domain;

import java.util.Date;

public class PermissionRequest {
    private Long requestId;
    private Long userId;
    private String userName;
    private String systemCode;
    private String featureCode;
    private String featureName;
    private Integer originalLevel;
    private Integer requestLevel;
    private String requestReason;
    private String status;
    private Integer isTemp;
    private Date requestTime;
    private String approveBy;
    private Date approveTime;
    private String approveNote;
    private Date rollbackTime;

    public Long getRequestId() { return requestId; }
    public void setRequestId(Long requestId) { this.requestId = requestId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getUserName() { return userName; }
    public void setUserName(String userName) { this.userName = userName; }
    public String getSystemCode() { return systemCode; }
    public void setSystemCode(String systemCode) { this.systemCode = systemCode; }
    public String getFeatureCode() { return featureCode; }
    public void setFeatureCode(String featureCode) { this.featureCode = featureCode; }
    public String getFeatureName() { return featureName; }
    public void setFeatureName(String featureName) { this.featureName = featureName; }
    public Integer getOriginalLevel() { return originalLevel; }
    public void setOriginalLevel(Integer originalLevel) { this.originalLevel = originalLevel; }
    public Integer getRequestLevel() { return requestLevel; }
    public void setRequestLevel(Integer requestLevel) { this.requestLevel = requestLevel; }
    public String getRequestReason() { return requestReason; }
    public void setRequestReason(String requestReason) { this.requestReason = requestReason; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Integer getIsTemp() { return isTemp; }
    public void setIsTemp(Integer isTemp) { this.isTemp = isTemp; }
    public Date getRequestTime() { return requestTime; }
    public void setRequestTime(Date requestTime) { this.requestTime = requestTime; }
    public String getApproveBy() { return approveBy; }
    public void setApproveBy(String approveBy) { this.approveBy = approveBy; }
    public Date getApproveTime() { return approveTime; }
    public void setApproveTime(Date approveTime) { this.approveTime = approveTime; }
    public String getApproveNote() { return approveNote; }
    public void setApproveNote(String approveNote) { this.approveNote = approveNote; }
    public Date getRollbackTime() { return rollbackTime; }
    public void setRollbackTime(Date rollbackTime) { this.rollbackTime = rollbackTime; }
}
