package com.ruoyi.distribute.domain;

import java.util.List;

public class DashboardOverview {

    private DashboardSummary summary;

    private List<DashboardTrendPoint> trend;

    private List<DashboardDistributionItem> typeDistribution;

    private List<DashboardDistributionItem> algorithmDistribution;

    private List<KeyDistributeRecord> recentFailures;

    private List<KeyDistributeRecord> recentChainResults;

    public DashboardSummary getSummary() {
        return summary;
    }

    public void setSummary(DashboardSummary summary) {
        this.summary = summary;
    }

    public List<DashboardTrendPoint> getTrend() {
        return trend;
    }

    public void setTrend(List<DashboardTrendPoint> trend) {
        this.trend = trend;
    }

    public List<DashboardDistributionItem> getTypeDistribution() {
        return typeDistribution;
    }

    public void setTypeDistribution(List<DashboardDistributionItem> typeDistribution) {
        this.typeDistribution = typeDistribution;
    }

    public List<DashboardDistributionItem> getAlgorithmDistribution() {
        return algorithmDistribution;
    }

    public void setAlgorithmDistribution(List<DashboardDistributionItem> algorithmDistribution) {
        this.algorithmDistribution = algorithmDistribution;
    }

    public List<KeyDistributeRecord> getRecentFailures() {
        return recentFailures;
    }

    public void setRecentFailures(List<KeyDistributeRecord> recentFailures) {
        this.recentFailures = recentFailures;
    }

    public List<KeyDistributeRecord> getRecentChainResults() {
        return recentChainResults;
    }

    public void setRecentChainResults(List<KeyDistributeRecord> recentChainResults) {
        this.recentChainResults = recentChainResults;
    }
}
