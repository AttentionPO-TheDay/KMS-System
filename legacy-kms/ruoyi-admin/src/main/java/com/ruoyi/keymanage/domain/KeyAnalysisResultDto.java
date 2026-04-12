package com.ruoyi.keymanage.domain;

import java.util.List;
import java.util.Map;

public class KeyAnalysisResultDto {
    private Keymanage baseInfo;
    private List<Map<String, Object>> distributeFootprints;
    private List<Map<String, Object>> operationTrails;

    public Keymanage getBaseInfo() {
        return baseInfo;
    }
    public void setBaseInfo(Keymanage baseInfo) {
        this.baseInfo = baseInfo;
    }
    public List<Map<String, Object>> getDistributeFootprints() {
        return distributeFootprints;
    }
    public void setDistributeFootprints(List<Map<String, Object>> distributeFootprints) {
        this.distributeFootprints = distributeFootprints;
    }
    public List<Map<String, Object>> getOperationTrails() {
        return operationTrails;
    }
    public void setOperationTrails(List<Map<String, Object>> operationTrails) {
        this.operationTrails = operationTrails;
    }
}
