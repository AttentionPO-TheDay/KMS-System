package com.ruoyi.distribute.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.distribute.service.IKeyDistributeDashboardService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/distribute/dashboard")
public class KeyDistributeDashboardController extends BaseController {

    @Autowired
    private IKeyDistributeDashboardService dashboardService;

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/overview")
    public AjaxResult overview() {
        Long userId = SecurityUtils.isAdmin(getUserId()) ? null : getUserId();
        return success(dashboardService.getOverview(userId));
    }
}
