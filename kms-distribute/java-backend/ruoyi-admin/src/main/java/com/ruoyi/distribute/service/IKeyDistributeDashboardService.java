package com.ruoyi.distribute.service;

import com.ruoyi.distribute.domain.DashboardOverview;

public interface IKeyDistributeDashboardService {

    DashboardOverview getOverview(Long userId);
}
