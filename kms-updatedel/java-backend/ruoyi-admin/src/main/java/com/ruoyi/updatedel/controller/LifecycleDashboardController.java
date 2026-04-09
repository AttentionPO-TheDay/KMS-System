package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lifecycle/keymanage/dashboard")
public class LifecycleDashboardController extends BaseController {
    private final KeyOperationRecordService keyOperationRecordService;

    public LifecycleDashboardController(KeyOperationRecordService keyOperationRecordService) {
        this.keyOperationRecordService = keyOperationRecordService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/summary")
    public AjaxResult summary() {
        return AjaxResult.success("查询成功", keyOperationRecordService.buildDashboardSummary());
    }
}
