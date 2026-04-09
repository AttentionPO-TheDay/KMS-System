package com.ruoyi.distribute.mapper;

import com.ruoyi.distribute.domain.DashboardDistributionItem;
import com.ruoyi.distribute.domain.DashboardSummary;
import com.ruoyi.distribute.domain.DashboardTrendPoint;
import com.ruoyi.distribute.domain.KeyDistributeRecord;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface KeyDistributeDashboardMapper {

    DashboardSummary selectDashboardSummary(@Param("userId") Long userId);

    List<DashboardTrendPoint> selectTrend(@Param("userId") Long userId,
                                          @Param("days") int days);

    List<DashboardDistributionItem> selectTypeDistribution(@Param("userId") Long userId,
                                                           @Param("days") int days);

    List<DashboardDistributionItem> selectAlgorithmDistribution(@Param("userId") Long userId,
                                                                @Param("days") int days);

    List<KeyDistributeRecord> selectRecentFailures(@Param("userId") Long userId,
                                                   @Param("limit") int limit);

    List<KeyDistributeRecord> selectRecentChainResults(@Param("userId") Long userId,
                                                       @Param("limit") int limit);
}
