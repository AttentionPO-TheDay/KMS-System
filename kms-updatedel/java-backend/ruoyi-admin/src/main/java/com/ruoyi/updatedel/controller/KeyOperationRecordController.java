package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lifecycle/operation-record")
public class KeyOperationRecordController extends BaseController {
    private final KeyOperationRecordService keyOperationRecordService;

    public KeyOperationRecordController(KeyOperationRecordService keyOperationRecordService) {
        this.keyOperationRecordService = keyOperationRecordService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(KeyOperationRecord query) {
        if (!(SecurityUtils.isAdmin(getUserId()) || com.ruoyi.framework.web.service.DemoIdentity.isCurrentAdmin())) {
            query.setUserId(getUserId());
        }
        startPage();
        return getDataTable(keyOperationRecordService.list(query));
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/receive/{recordId}")
    public AjaxResult receive(@PathVariable Long recordId) {
        keyOperationRecordService.receive(recordId, getUserId());
        return AjaxResult.success("接收成功");
    }
}
