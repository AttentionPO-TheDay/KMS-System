package com.ruoyi.framework.security.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 登录失败限制服务
 * 防止暴力破解攻击
 * 
 * @author ruoyi
 * @date 2026-01-22
 */
@Service
public class LoginAttemptService {

    private static final Logger log = LoggerFactory.getLogger(LoginAttemptService.class);

    // 最大尝试次数
    private static final int MAX_ATTEMPT = 5;

    // 锁定时长（分钟）
    private static final long LOCK_TIME_DURATION = 15;

    // 失败次数缓存
    private final ConcurrentHashMap<String, Integer> attemptsCache = new ConcurrentHashMap<>();

    // 锁定时间缓存
    private final ConcurrentHashMap<String, Long> lockTimeCache = new ConcurrentHashMap<>();

    /**
     * 登录成功，清除失败记录
     * 
     * @param key 用户标识（用户名+IP）
     */
    public void loginSucceeded(String key) {
        attemptsCache.remove(key);
        lockTimeCache.remove(key);
        log.debug("登录成功，清除失败记录: {}", key);
    }

    /**
     * 登录失败，记录失败次数
     * 
     * @param key 用户标识（用户名+IP）
     */
    public void loginFailed(String key) {
        int attempts = attemptsCache.getOrDefault(key, 0);
        attempts++;
        attemptsCache.put(key, attempts);

        if (attempts >= MAX_ATTEMPT) {
            lockTimeCache.put(key, System.currentTimeMillis());
            log.warn("登录失败次数达到上限，账户已锁定: key={}, 失败次数={}", key, attempts);
        } else {
            log.info("登录失败: key={}, 失败次数={}/{}", key, attempts, MAX_ATTEMPT);
        }
    }

    /**
     * 判断用户是否被锁定
     * 
     * @param key 用户标识（用户名+IP）
     * @return true=已锁定, false=未锁定
     */
    public boolean isBlocked(String key) {
        if (!lockTimeCache.containsKey(key)) {
            return false;
        }

        long lockTime = lockTimeCache.get(key);
        long elapsedTime = System.currentTimeMillis() - lockTime;
        long lockDuration = TimeUnit.MINUTES.toMillis(LOCK_TIME_DURATION);

        if (elapsedTime > lockDuration) {
            // 锁定时间已过，解除锁定
            attemptsCache.remove(key);
            lockTimeCache.remove(key);
            log.info("锁定时间已过，解除账户锁定: {}", key);
            return false;
        }

        // 计算剩余锁定时间
        long remainingMinutes = (lockDuration - elapsedTime) / 60000;
        log.debug("账户仍处于锁定状态: key={}, 剩余时间={}分钟", key, remainingMinutes);
        return true;
    }

    /**
     * 获取剩余尝试次数
     * 
     * @param key 用户标识（用户名+IP）
     * @return 剩余次数
     */
    public int getRemainingAttempts(String key) {
        int attempts = attemptsCache.getOrDefault(key, 0);
        return Math.max(0, MAX_ATTEMPT - attempts);
    }

    /**
     * 获取剩余锁定时间（分钟）
     * 
     * @param key 用户标识（用户名+IP）
     * @return 剩余分钟数，如果未锁定则返回0
     */
    public long getRemainingLockTime(String key) {
        if (!lockTimeCache.containsKey(key)) {
            return 0;
        }

        long lockTime = lockTimeCache.get(key);
        long elapsedTime = System.currentTimeMillis() - lockTime;
        long lockDuration = TimeUnit.MINUTES.toMillis(LOCK_TIME_DURATION);

        if (elapsedTime > lockDuration) {
            return 0;
        }

        return (lockDuration - elapsedTime) / 60000;
    }
}
