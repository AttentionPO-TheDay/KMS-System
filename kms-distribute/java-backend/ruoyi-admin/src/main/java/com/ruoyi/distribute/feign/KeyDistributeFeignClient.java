package com.ruoyi.distribute.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.distribute.domain.KeyDistributeRecord;

/**
 * 密钥分发系统 Feign 客户端
 * 供其他系统调用密钥分发记录服务
 */
@FeignClient(name = "kms-distribute", url = "${kms.distribute.url:http://localhost:8083}")
public interface KeyDistributeFeignClient {

    /**
     * 查询分发记录列表
     */
    @GetMapping("/distribute/record/list")
    TableDataInfo list(@RequestParam(required = false) Integer pageNum,
                       @RequestParam(required = false) Integer pageSize,
                       @RequestParam(required = false) Long userId,
                       @RequestParam(required = false) String userName,
                       @RequestParam(required = false) String keyName,
                       @RequestParam(required = false) String distributeType,
                       @RequestParam(required = false) String distributeStatus);

    /**
     * 获取分发记录详情
     */
    @GetMapping("/distribute/record/{recordId}")
    AjaxResult getInfo(@PathVariable("recordId") Long recordId);

    /**
     * 新增分发记录
     */
    @PostMapping("/distribute/record")
    AjaxResult add(@RequestBody KeyDistributeRecord record);

    /**
     * 批量新增分发记录
     */
    @PostMapping("/distribute/record/batch")
    AjaxResult addBatch(@RequestBody java.util.List<KeyDistributeRecord> records);

    /**
     * 修改分发记录
     */
    @PutMapping("/distribute/record")
    AjaxResult edit(@RequestBody KeyDistributeRecord record);
}
