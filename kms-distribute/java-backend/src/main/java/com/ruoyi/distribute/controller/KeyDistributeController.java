package com.ruoyi.distribute.controller;

import com.ruoyi.common.core.domain.R;
import com.ruoyi.distribute.domain.KeyDistributeRecord;
import com.ruoyi.distribute.service.IKeyDistributeService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 密钥分发记录Controller
 */
@RestController
@RequestMapping("/distribute/record")
public class KeyDistributeController {

    @Autowired
    private IKeyDistributeService keyDistributeService;

    /**
     * 查询分发记录列表
     */
    @GetMapping("/list")
    public R<List<KeyDistributeRecord>> list(KeyDistributeRecord record) {
        List<KeyDistributeRecord> list = keyDistributeService.selectKeyDistributeRecordList(record);
        return R.ok(list);
    }

    /**
     * 获取分发记录详情
     */
    @GetMapping("/{recordId}")
    public R<KeyDistributeRecord> getInfo(@PathVariable("recordId") Long recordId) {
        return R.ok(keyDistributeService.selectKeyDistributeRecordById(recordId));
    }

    /**
     * 新增分发记录
     */
    @PostMapping
    public R<Void> add(@RequestBody KeyDistributeRecord record) {
        return R.ok(keyDistributeService.insertKeyDistributeRecord(record) > 0);
    }

    /**
     * 批量新增分发记录
     */
    @PostMapping("/batch")
    public R<Void> addBatch(@RequestBody List<KeyDistributeRecord> records) {
        return R.ok(keyDistributeService.insertKeyDistributeRecordBatch(records) > 0);
    }

    /**
     * 修改分发记录
     */
    @PutMapping
    public R<Void> edit(@RequestBody KeyDistributeRecord record) {
        return R.ok(keyDistributeService.updateKeyDistributeRecord(record) > 0);
    }

    /**
     * 删除分发记录
     */
    @DeleteMapping("/{recordId}")
    public R<Void> remove(@PathVariable Long recordId) {
        return R.ok(keyDistributeService.deleteKeyDistributeRecordById(recordId) > 0);
    }
}
