package com.ruoyi.distribute.controller;

import java.util.List;
import javax.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.distribute.domain.KeyDistributeRecord;
import com.ruoyi.distribute.service.IKeyDistributeService;

/**
 * 密钥分发记录Controller
 */
@RestController
@RequestMapping("/distribute/record")
public class KeyDistributeController extends BaseController {

    @Autowired
    private IKeyDistributeService keyDistributeService;

    /**
     * 查询分发记录列表
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(KeyDistributeRecord record) {
        startPage();
        List<KeyDistributeRecord> list = keyDistributeService.selectKeyDistributeRecordList(record);
        return getDataTable(list);
    }

    /**
     * 导出分发记录列表
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥分发记录", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, KeyDistributeRecord record) {
        List<KeyDistributeRecord> list = keyDistributeService.selectKeyDistributeRecordList(record);
        ExcelUtil<KeyDistributeRecord> util = new ExcelUtil<KeyDistributeRecord>(KeyDistributeRecord.class);
        util.exportExcel(response, list, "密钥分发记录数据");
    }

    /**
     * 获取分发记录详情
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{recordId}")
    public AjaxResult getInfo(@PathVariable("recordId") Long recordId) {
        return success(keyDistributeService.selectKeyDistributeRecordById(recordId));
    }

    /**
     * 新增分发记录
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥分发记录", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody KeyDistributeRecord record) {
        record.setCreateBy(getUsername());
        return toAjax(keyDistributeService.insertKeyDistributeRecord(record));
    }

    /**
     * 批量新增分发记录
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥分发记录", businessType = BusinessType.INSERT)
    @PostMapping("/batch")
    public AjaxResult addBatch(@RequestBody List<KeyDistributeRecord> records) {
        String username = getUsername();
        for (KeyDistributeRecord record : records) {
            record.setCreateBy(username);
        }
        return toAjax(keyDistributeService.insertKeyDistributeRecordBatch(records));
    }

    /**
     * 修改分发记录
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥分发记录", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody KeyDistributeRecord record) {
        record.setUpdateBy(getUsername());
        return toAjax(keyDistributeService.updateKeyDistributeRecord(record));
    }

    /**
     * 删除分发记录
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥分发记录", businessType = BusinessType.DELETE)
    @DeleteMapping("/{recordId}")
    public AjaxResult remove(@PathVariable Long recordId) {
        return toAjax(keyDistributeService.deleteKeyDistributeRecordById(recordId));
    }
}
