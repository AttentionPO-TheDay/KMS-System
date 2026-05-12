package com.ruoyi.generate.controller;

import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/generate")
public class InternalGenerateController {
    private static final DateTimeFormatter[] TIME_FORMATTERS = new DateTimeFormatter[] {
        DateTimeFormatter.ISO_DATE_TIME,
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss", Locale.ROOT)
    };

    private final GenerateKeyService generateKeyService;

    @Value("${kms.go-backend.internal-token:kms-generate-internal-secret-2026}")
    private String internalToken;

    public InternalGenerateController(GenerateKeyService generateKeyService) {
        this.generateKeyService = generateKeyService;
    }

    @GetMapping("/keys/recent")
    public Map<String, Object> recentKeys(@RequestHeader(value = "X-Internal-Token", required = false) String token,
                                          @RequestParam String userName,
                                          @RequestParam(defaultValue = "200") int limit,
                                          @RequestParam(required = false) String createdAfter,
                                          @RequestParam(required = false) String encrytName,
                                          @RequestParam(required = false) String keyName,
                                          @RequestParam(required = false) String ua) {
        requireAuthorized(token);

        Keymanage query = new Keymanage();
        query.setUserName(userName);
        if (encrytName != null && !encrytName.trim().isEmpty()) {
            query.setEncrytName(encrytName.trim());
        }
        if (keyName != null && !keyName.trim().isEmpty()) {
            query.setKeyName(keyName.trim());
        }

        String expectedKeyName = trimToNull(keyName);
        String expectedUa = trimToNull(ua);
        LocalDateTime createdAfterTime = parseTime(createdAfter);
        List<Keymanage> all = generateKeyService.selectKeyList(query);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Keymanage key : all) {
            if (createdAfterTime != null) {
                LocalDateTime createdAt = parseTime(key.getCreTime());
                if (createdAt == null || createdAt.isBefore(createdAfterTime)) {
                    continue;
                }
            }
            if (expectedKeyName != null && !expectedKeyName.equals(key.getKeyName())) {
                continue;
            }
            if (expectedUa != null && !expectedUa.equals(key.getuA())) {
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("keyId", key.getKeyId());
            item.put("userName", key.getUserName());
            item.put("encrytName", key.getEncrytName());
            item.put("keyName", key.getKeyName());
            item.put("keyUse", key.getKeyUse());
            item.put("keyDomain", key.getKeyDomain());
            item.put("ua", key.getuA());
            item.put("status", key.getStatus());
            item.put("createdAt", key.getCreTime());
            items.add(item);
            if (items.size() >= Math.max(1, limit)) {
                break;
            }
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

    private String trimToNull(String value) {
        if (value == null || value.trim().isEmpty()) {
            return null;
        }
        return value.trim();
    }

    private LocalDateTime parseTime(String value) {
        if (value == null || value.trim().isEmpty()) {
            return null;
        }
        String text = value.trim();
        for (DateTimeFormatter formatter : TIME_FORMATTERS) {
            try {
                return LocalDateTime.parse(text, formatter);
            } catch (DateTimeParseException ignored) {
            }
        }
        try {
            return LocalDateTime.ofEpochSecond(Long.parseLong(text), 0, ZoneOffset.UTC);
        } catch (NumberFormatException ignored) {
            return null;
        }
    }
}
