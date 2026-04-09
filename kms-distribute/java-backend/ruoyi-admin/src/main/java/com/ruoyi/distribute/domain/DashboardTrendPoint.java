package com.ruoyi.distribute.domain;

public class DashboardTrendPoint {

    private String statDate;

    private Long totalCount;

    private Long chainCompletedCount;

    private Long chainFailedCount;

    public String getStatDate() {
        return statDate;
    }

    public void setStatDate(String statDate) {
        this.statDate = statDate;
    }

    public Long getTotalCount() {
        return totalCount;
    }

    public void setTotalCount(Long totalCount) {
        this.totalCount = totalCount;
    }

    public Long getChainCompletedCount() {
        return chainCompletedCount;
    }

    public void setChainCompletedCount(Long chainCompletedCount) {
        this.chainCompletedCount = chainCompletedCount;
    }

    public Long getChainFailedCount() {
        return chainFailedCount;
    }

    public void setChainFailedCount(Long chainFailedCount) {
        this.chainFailedCount = chainFailedCount;
    }
}
