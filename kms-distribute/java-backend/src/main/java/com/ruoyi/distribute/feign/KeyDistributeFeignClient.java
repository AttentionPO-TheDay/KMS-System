package com.ruoyi.distribute.feign;

import com.ruoyi.common.core.domain.R;
import com.ruoyi.distribute.domain.KeyDistributeRecord;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 密钥分发系统 Feign 客户端
 * 供其他系统调用密钥分发记录服务
 */
@FeignClient(name = "kms-distribute", url = "${kms.distribute.url:http://localhost:8082}")
public interface KeyDistributeFeignClient {

    /**
     * 查询分发记录列表
     */
    @GetMapping("/distribute/record/list")
    R<List<KeyDistributeRecord>> list(@RequestParam(required = false) Long userId,
                                       @RequestParam(required = false) String userName,
                                       @RequestParam(required = false) String keyName,
                                       @RequestParam(required = false) String distributeType,
                                       @RequestParam(required = false) String distributeStatus);

    /**
     * 获取分发记录详情
     */
    @GetMapping("/distribute/record/{recordId}")
    R<KeyDistributeRecord> getInfo(@PathVariable("recordId") Long recordId);

    /**
     * 新增分发记录
     */
    @PostMapping("/distribute/record")
    R<Void> add(@RequestBody KeyDistributeRecord record);

    /**
     * 批量新增分发记录
     */
    @PostMapping("/distribute/record/batch")
    R<Void> addBatch(@RequestBody List<KeyDistributeRecord> records);

    /**
     * 修改分发记录
     */
    @PutMapping("/distribute/record")
    R<Void> edit(@RequestBody KeyDistributeRecord record);
}
