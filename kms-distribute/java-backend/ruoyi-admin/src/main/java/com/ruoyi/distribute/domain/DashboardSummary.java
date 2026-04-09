package com.ruoyi.distribute.domain;

public class DashboardSummary {

    private Long totalRecords;

    private Long todayRecords;

    private Long chainCompletedRecords;

    private Long chainFailedRecords;

    public Long getTotalRecords() {
        return totalRecords;
    }

    public void setTotalRecords(Long totalRecords) {
        this.totalRecords = totalRecords;
    }

    public Long getTodayRecords() {
        return todayRecords;
    }

    public void setTodayRecords(Long todayRecords) {
        this.todayRecords = todayRecords;
    }

    public Long getChainCompletedRecords() {
        return chainCompletedRecords;
    }

    public void setChainCompletedRecords(Long chainCompletedRecords) {
        this.chainCompletedRecords = chainCompletedRecords;
    }

    public Long getChainFailedRecords() {
        return chainFailedRecords;
    }

    public void setChainFailedRecords(Long chainFailedRecords) {
        this.chainFailedRecords = chainFailedRecords;
    }
}
