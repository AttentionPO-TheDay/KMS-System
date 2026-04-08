package com.ruoyi.generate.controller;

import com.ruoyi.common.annotation.Anonymous;
import com.ruoyi.common.core.domain.AjaxResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 健康检查控制器
 */
@RestController
@RequestMapping("/generate")
public class HealthController {

    /**
     * 健康检查接口
     * GET /generate/ping
     */
    @Anonymous
    @GetMapping("/ping")
    public AjaxResult ping() {
        return AjaxResult.success("kms-generate Java Backend is running")
                .put("service", "kms-generate")
                .put("version", "1.0.0")
                .put("status", "UP");
    }
}
