package com.ruoyi.updatedel.controller;

import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.LifecycleService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/lifecycle")
public class InternalLifecycleController {
    private final LifecycleService lifecycleService;

    @Value("${kms.go-backend.internal-token:kms-generate-internal-secret-2026}")
    private String internalToken;

    public InternalLifecycleController(LifecycleService lifecycleService) {
        this.lifecycleService = lifecycleService;
    }

    @GetMapping("/key-status")
    public Map<String, Object> keyStatus(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                         @RequestParam("keyIds") List<Long> keyIds) {
        requireAuthorized(token);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Long keyId : keyIds) {
            Keymanage key = lifecycleService.findById(keyId).orElse(null);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("keyId", keyId);
            item.put("exists", key != null);
            item.put("status", key == null ? null : key.getStatus());
            item.put("chainStatus", key == null ? null : key.getChainStatus());
            item.put("updatedAt", key == null ? null : key.getUpdTime());
            items.add(item);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", items);
        return payload;
    }

    private void requireAuthorized(String token) {
        if (token == null || !internalToken.equals(token)) {
            throw new IllegalArgumentException("invalid internal token");
        }
    }
}
