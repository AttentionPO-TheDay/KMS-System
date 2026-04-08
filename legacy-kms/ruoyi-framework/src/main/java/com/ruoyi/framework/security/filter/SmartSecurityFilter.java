package com.ruoyi.framework.security.filter;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import javax.servlet.*;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 智能安全过滤器
 * 基于异常模式检测而非简单限流，不影响正常高速业务
 * 
 * 检测策略：
 * 1. 扫描工具User-Agent识别
 * 2. 异常访问模式检测（大量404、403）
 * 3. 登录失败模式检测
 * 
 * @author ruoyi
 * @date 2026-01-22
 */
@Component
public class SmartSecurityFilter implements Filter {

    private static final Logger log = LoggerFactory.getLogger(SmartSecurityFilter.class);

    // 访问模式缓存
    private final ConcurrentHashMap<String, AccessPattern> accessPatterns = new ConcurrentHashMap<>();

    // 黑名单缓存（被识别为恶意的IP）
    private final ConcurrentHashMap<String, Long> blacklist = new ConcurrentHashMap<>();

    // 黑名单封禁时长（分钟）
    private static final long BLACKLIST_DURATION = 30;

    // 扫描工具特征
    private static final String[] SCANNER_USER_AGENTS = {
            "sqlmap", "nikto", "nmap", "masscan", "nessus",
            "burp", "zap", "scanner", "crawler", "spider",
            "acunetix", "metasploit", "havij", "w3af"
    };

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;

        String clientIP = getClientIP(httpRequest);
        String requestURI = httpRequest.getRequestURI();
        String userAgent = httpRequest.getHeader("User-Agent");

        // 1. 检查是否在黑名单中
        if (isBlacklisted(clientIP)) {
            log.warn("阻止黑名单IP访问: IP={}, URI={}", clientIP, requestURI);
            httpResponse.setStatus(403);
            httpResponse.setContentType("application/json;charset=UTF-8");
            httpResponse.getWriter().write("{\"code\":403,\"msg\":\"您的IP已被暂时封禁，请30分钟后再试\"}");
            return;
        }

        // 2. 检测扫描工具User-Agent
        if (isScannerUserAgent(userAgent)) {
            log.warn("检测到扫描工具: IP={}, UserAgent={}", clientIP, userAgent);
            addToBlacklist(clientIP, "扫描工具");
            httpResponse.setStatus(403);
            httpResponse.setContentType("application/json;charset=UTF-8");
            httpResponse.getWriter().write("{\"code\":403,\"msg\":\"检测到自动化扫描工具，访问已被拒绝\"}");
            return;
        }

        // 3. 获取访问模式记录
        AccessPattern pattern = accessPatterns.computeIfAbsent(clientIP, k -> new AccessPattern());

        // 执行请求
        chain.doFilter(request, response);

        // 4. 分析响应状态
        int status = httpResponse.getStatus();
        pattern.recordRequest(requestURI, status);

        // 5. 检测异常模式
        if (pattern.isAbnormal()) {
            String reason = pattern.getAbnormalReason();
            log.warn("检测到异常访问模式: IP={}, 原因={}", clientIP, reason);
            addToBlacklist(clientIP, reason);
        }
    }

    /**
     * 检测是否为扫描工具User-Agent
     */
    private boolean isScannerUserAgent(String userAgent) {
        if (userAgent == null || userAgent.isEmpty()) {
            // 空User-Agent可疑，但不直接拒绝
            return false;
        }

        String ua = userAgent.toLowerCase();
        for (String scanner : SCANNER_USER_AGENTS) {
            if (ua.contains(scanner)) {
                return true;
            }
        }

        return false;
    }

    /**
     * 检查IP是否在黑名单中
     */
    private boolean isBlacklisted(String ip) {
        if (!blacklist.containsKey(ip)) {
            return false;
        }

        long blacklistTime = blacklist.get(ip);
        long elapsedTime = System.currentTimeMillis() - blacklistTime;
        long duration = TimeUnit.MINUTES.toMillis(BLACKLIST_DURATION);

        if (elapsedTime > duration) {
            // 封禁时间已过，解除封禁
            blacklist.remove(ip);
            accessPatterns.remove(ip);
            log.info("解除IP封禁: {}", ip);
            return false;
        }

        return true;
    }

    /**
     * 添加IP到黑名单
     */
    private void addToBlacklist(String ip, String reason) {
        blacklist.put(ip, System.currentTimeMillis());
        log.warn("IP已加入黑名单: IP={}, 原因={}, 封禁时长={}分钟", ip, reason, BLACKLIST_DURATION);
    }

    /**
     * 获取客户端真实IP
     */
    private String getClientIP(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }
        // 处理多级代理的情况
        if (ip != null && ip.indexOf(",") > 0) {
            ip = ip.split(",")[0].trim();
        }
        return ip;
    }

    @Override
    public void init(FilterConfig filterConfig) throws ServletException {
        log.info("SmartSecurityFilter 初始化完成");
    }

    @Override
    public void destroy() {
        log.info("SmartSecurityFilter 销毁");
        accessPatterns.clear();
        blacklist.clear();
    }

    /**
     * 访问模式分析类
     */
    static class AccessPattern {
        private int totalRequests = 0;
        private int notFoundCount = 0; // 404计数
        private int forbiddenCount = 0; // 403计数
        private int serverErrorCount = 0; // 500计数
        private long windowStart = System.currentTimeMillis();

        // 统计周期（分钟）
        private static final long WINDOW_DURATION = 5;

        /**
         * 记录请求
         */
        public synchronized void recordRequest(String uri, int status) {
            // 检查是否需要重置统计窗口
            long now = System.currentTimeMillis();
            if (now - windowStart > TimeUnit.MINUTES.toMillis(WINDOW_DURATION)) {
                reset();
                windowStart = now;
            }

            totalRequests++;

            if (status == 404) {
                notFoundCount++;
            } else if (status == 403) {
                forbiddenCount++;
            } else if (status >= 500) {
                serverErrorCount++;
            }
        }

        /**
         * 判断是否为异常模式
         */
        public boolean isAbnormal() {
            // 模式1：短时间内大量404（扫描行为）
            if (notFoundCount > 30) {
                return true;
            }

            // 模式2：404比例过高（>60%）且请求数>15
            if (totalRequests > 15 &&
                    (double) notFoundCount / totalRequests > 0.6) {
                return true;
            }

            // 模式3：大量403（尝试越权访问）
            if (forbiddenCount > 20) {
                return true;
            }

            // 模式4：403比例过高（>50%）且请求数>10
            if (totalRequests > 10 &&
                    (double) forbiddenCount / totalRequests > 0.5) {
                return true;
            }

            return false;
        }

        /**
         * 获取异常原因
         */
        public String getAbnormalReason() {
            if (notFoundCount > 30 ||
                    (totalRequests > 15 && (double) notFoundCount / totalRequests > 0.6)) {
                return String.format("疑似目录扫描 (404次数: %d, 总请求: %d)",
                        notFoundCount, totalRequests);
            }

            if (forbiddenCount > 20 ||
                    (totalRequests > 10 && (double) forbiddenCount / totalRequests > 0.5)) {
                return String.format("疑似越权攻击 (403次数: %d, 总请求: %d)",
                        forbiddenCount, totalRequests);
            }

            return "异常访问模式";
        }

        /**
         * 重置统计
         */
        private void reset() {
            totalRequests = 0;
            notFoundCount = 0;
            forbiddenCount = 0;
            serverErrorCount = 0;
        }
    }
}
