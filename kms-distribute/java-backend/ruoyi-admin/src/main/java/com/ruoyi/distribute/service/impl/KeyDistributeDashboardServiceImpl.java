package com.ruoyi.distribute.service.impl;

import com.ruoyi.distribute.domain.DashboardOverview;
import com.ruoyi.distribute.mapper.KeyDistributeDashboardMapper;
import com.ruoyi.distribute.service.IKeyDistributeDashboardService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class KeyDistributeDashboardServiceImpl implements IKeyDistributeDashboardService {

    private static final int DEFAULT_DASHBOARD_WINDOW_DAYS = 6;

    private static final int DEFAULT_RECENT_LIMIT = 10;

    @Autowired
    private KeyDistributeDashboardMapper dashboardMapper;

    @Override
    public DashboardOverview getOverview(Long userId) {
        DashboardOverview overview = new DashboardOverview();
        overview.setSummary(dashboardMapper.selectDashboardSummary(userId));
        overview.setTrend(dashboardMapper.selectTrend(userId, DEFAULT_DASHBOARD_WINDOW_DAYS));
        overview.setTypeDistribution(dashboardMapper.selectTypeDistribution(userId, DEFAULT_DASHBOARD_WINDOW_DAYS));
        overview.setAlgorithmDistribution(dashboardMapper.selectAlgorithmDistribution(userId, DEFAULT_DASHBOARD_WINDOW_DAYS));
        overview.setRecentFailures(dashboardMapper.selectRecentFailures(userId, DEFAULT_RECENT_LIMIT));
        overview.setRecentChainResults(dashboardMapper.selectRecentChainResults(userId, DEFAULT_RECENT_LIMIT));
        return overview;
    }
}
