package com.ruoyi.generate.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

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
    @GetMapping("/ping")
    public ResponseEntity<Map<String, Object>> ping() {
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "kms-generate Java Backend is running");
        result.put("service", "kms-generate");
        result.put("version", "1.0.0");
        result.put("status", "UP");
        return ResponseEntity.ok(result);
    }
}
