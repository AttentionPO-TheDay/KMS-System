package com.ruoyi.framework.web.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.servlet.http.Cookie;
import javax.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DemoBoundary {
    public static final String COOKIE = "KMS-Demo-Session";
    @Value("${KMS_DEMO_ENABLED:false}") private boolean enabled;
    @Value("${INTERNAL_TOKEN:}") private String internalToken;
    @Value("${KMS_DEMO_ALLOWED_HOSTS:127.0.0.1:8088,localhost:8088}") private String hosts;
    @Value("${KMS_DEMO_ALLOWED_ORIGINS:http://127.0.0.1:8088,http://localhost:8088}") private String origins;
    @Value("${KMS_DEMO_COOKIE_SECURE:false}") private boolean secure;

    public boolean isDemo(HttpServletRequest request) {
        return "demo".equals(request.getHeader("X-Kms-Entry-Mode"));
    }

    public void requireGateway(HttpServletRequest request) {
        if (!enabled || !isDemo(request) || !same(internalToken, request.getHeader("X-Kms-Demo-Gateway"))
                || !listed(hosts, request.getHeader("Host"))) {
            throw new IllegalArgumentException("DEMO_BOUNDARY_REJECTED");
        }
        if (request.getHeader("Origin") != null) requireOrigin(request);
    }

    public void requireOrigin(HttpServletRequest request) {
        if (!listed(origins, request.getHeader("Origin"))) throw new IllegalArgumentException("DEMO_ORIGIN_REJECTED");
    }

    public void requireInternal(String token) {
        if (!enabled || !same(internalToken, token)) throw new IllegalArgumentException("DEMO_INTERNAL_REJECTED");
    }

    public String sessionId(HttpServletRequest request) {
        if (request.getCookies() != null) for (Cookie cookie : request.getCookies()) {
            if (COOKIE.equals(cookie.getName()) && cookie.getValue().matches("[A-Za-z0-9_-]{43}")) return cookie.getValue();
        }
        return null;
    }

    public boolean isSecure() { return secure; }
    public static boolean mutation(HttpServletRequest request) {
        return !Arrays.asList("GET", "HEAD", "OPTIONS").contains(request.getMethod());
    }
    public static boolean same(String expected, String actual) {
        return expected != null && !expected.isEmpty() && actual != null
                && MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), actual.getBytes(StandardCharsets.UTF_8));
    }
    private boolean listed(String list, String value) {
        return value != null && Arrays.stream(list.split(",")).map(String::trim).anyMatch(value::equals);
    }
}
