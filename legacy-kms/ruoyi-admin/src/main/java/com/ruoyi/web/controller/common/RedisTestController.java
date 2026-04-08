package com.ruoyi.web.controller.common;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.core.domain.AjaxResult;

/**
 * Redis测试
 */
@RestController
public class RedisTestController {
    @Autowired(required = false)
    private RedisTemplate<Object, Object> redisTemplate;

    @GetMapping("/testRedis")
    public AjaxResult testRedis() {
        try {
            if (redisTemplate == null) {
                return AjaxResult.error("RedisTemplate未注入，Redis可能未配置");
            }

            // 测试写入
            redisTemplate.opsForValue().set("test:key", "test-value");

            // 测试读取
            String value = (String) redisTemplate.opsForValue().get("test:key");

            if ("test-value".equals(value)) {
                return AjaxResult.success("Redis连接正常，读写测试成功！值: " + value);
            } else {
                return AjaxResult.error("Redis读写测试失败，期望: test-value，实际: " + value);
            }
        } catch (Exception e) {
            return AjaxResult.error("Redis连接失败: " + e.getMessage());
        }
    }
}
