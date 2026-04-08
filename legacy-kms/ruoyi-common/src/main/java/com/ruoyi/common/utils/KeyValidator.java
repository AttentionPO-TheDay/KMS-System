package com.ruoyi.common.utils;

import com.ruoyi.common.exception.KeyValidationException;
import java.math.BigInteger;

/**
 * 密钥验证工具类
 * 提供密钥长度、格式、椭圆曲线点等验证功能
 * 
 * @author ruoyi
 * @date 2026-01-22
 */
public class KeyValidator {

    // SM2椭圆曲线参数 (GBT 32918.5-2017)
    private static final BigInteger SM2_P = new BigInteger(
            "FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF", 16);
    private static final BigInteger SM2_A = new BigInteger(
            "FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC", 16);
    private static final BigInteger SM2_B = new BigInteger(
            "28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93", 16);
    private static final BigInteger SM2_N = new BigInteger(
            "FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16);

    // 常量定义
    private static final int SM2_PUBLIC_KEY_LENGTH = 130; // 04 + 64字符x + 64字符y
    private static final int SM2_PRIVATE_KEY_LENGTH = 64;
    private static final String SM2_PUBLIC_KEY_PREFIX = "04";
    private static final int MIN_USERNAME_LENGTH = 3;
    private static final int MAX_USERNAME_LENGTH = 30;
    private static final int MIN_PASSWORD_LENGTH = 6;
    private static final int MAX_PASSWORD_LENGTH = 20;

    /**
     * 验证密钥长度
     * 
     * @param key            密钥字符串
     * @param expectedLength 期望长度
     * @param keyType        密钥类型（用于错误提示）
     * @throws KeyValidationException 长度不匹配时抛出
     */
    public static void validateKeyLength(String key, int expectedLength, String keyType) {
        if (key == null || key.isEmpty()) {
            throw KeyValidationException.invalidFormat(keyType, "密钥不能为空");
        }

        int actualLength = key.length();
        if (actualLength != expectedLength) {
            throw KeyValidationException.invalidLength(keyType, expectedLength, actualLength);
        }
    }

    /**
     * 验证SM2公钥格式
     * 要求：
     * 1. 长度为130字符
     * 2. 以"04"开头（非压缩格式）
     * 3. 全部为十六进制字符
     * 4. 点在椭圆曲线上
     * 
     * @param publicKey SM2公钥（十六进制字符串）
     * @throws KeyValidationException 验证失败时抛出
     */
    public static void validateSM2PublicKey(String publicKey) {
        // 1. 非空检查
        if (StringUtils.isEmpty(publicKey)) {
            throw KeyValidationException.invalidFormat("SM2公钥", "公钥不能为空");
        }

        // 2. 长度检查
        if (publicKey.length() != SM2_PUBLIC_KEY_LENGTH) {
            throw KeyValidationException.invalidLength("SM2公钥", SM2_PUBLIC_KEY_LENGTH, publicKey.length());
        }

        // 3. 前缀检查
        if (!publicKey.startsWith(SM2_PUBLIC_KEY_PREFIX)) {
            String actualPrefix = publicKey.substring(0, Math.min(2, publicKey.length()));
            throw KeyValidationException.invalidPrefix(SM2_PUBLIC_KEY_PREFIX, actualPrefix);
        }

        // 4. 十六进制格式检查
        if (!isHexString(publicKey)) {
            throw KeyValidationException.invalidFormat("SM2公钥", "必须是十六进制字符串");
        }

        // 5. 椭圆曲线点验证
        if (!isPointOnSM2Curve(publicKey)) {
            throw KeyValidationException.invalidCurvePoint("公钥点不在SM2椭圆曲线上");
        }
    }

    /**
     * 验证SM2私钥格式
     * 要求：
     * 1. 长度为64字符
     * 2. 全部为十六进制字符
     * 3. 在有效范围内 (1 < d < n-1)
     * 
     * @param privateKey SM2私钥（十六进制字符串）
     * @throws KeyValidationException 验证失败时抛出
     */
    public static void validateSM2PrivateKey(String privateKey) {
        // 1. 非空检查
        if (privateKey == null || privateKey.isEmpty()) {
            throw KeyValidationException.invalidFormat("SM2私钥", "私钥不能为空");
        }

        // 2. 长度检查
        if (privateKey.length() != SM2_PRIVATE_KEY_LENGTH) {
            throw KeyValidationException.invalidLength("SM2私钥", SM2_PRIVATE_KEY_LENGTH, privateKey.length());
        }

        // 3. 十六进制格式检查
        if (!isHexString(privateKey)) {
            throw KeyValidationException.invalidFormat("SM2私钥", "必须是十六进制字符串");
        }

        // 4. 范围检查 (1 < d < n-1)
        try {
            BigInteger d = new BigInteger(privateKey, 16);
            if (d.compareTo(BigInteger.ONE) <= 0 || d.compareTo(SM2_N.subtract(BigInteger.ONE)) >= 0) {
                throw KeyValidationException.invalidFormat("SM2私钥", "私钥必须在有效范围内 (1 < d < n-1)");
            }
        } catch (NumberFormatException e) {
            throw KeyValidationException.invalidFormat("SM2私钥", "十六进制格式错误");
        }
    }

    /**
     * 验证用户凭证（用户名和密码）
     * 
     * @param username 用户名
     * @param password 密码
     * @throws KeyValidationException 验证失败时抛出
     */
    public static void validateCredentials(String username, String password) {
        // 用户名验证
        if (username == null || username.isEmpty()) {
            throw KeyValidationException.invalidCredentials("用户名", "不能为空");
        }
        if (username.length() < MIN_USERNAME_LENGTH || username.length() > MAX_USERNAME_LENGTH) {
            throw KeyValidationException.invalidCredentials("用户名",
                    String.format("长度必须在%d-%d字符之间", MIN_USERNAME_LENGTH, MAX_USERNAME_LENGTH));
        }

        // 密码验证
        if (password == null || password.isEmpty()) {
            throw KeyValidationException.invalidCredentials("密码", "不能为空");
        }
        if (password.length() < MIN_PASSWORD_LENGTH || password.length() > MAX_PASSWORD_LENGTH) {
            throw KeyValidationException.invalidCredentials("密码",
                    String.format("长度必须在%d-%d字符之间", MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH));
        }
    }

    /**
     * 检查点是否在SM2椭圆曲线上
     * 椭圆曲线方程: y² ≡ x³ + ax + b (mod p)
     * 
     * @param hexPoint 十六进制格式的点（04 + x坐标 + y坐标）
     * @return true 如果点在曲线上
     */
    public static boolean isPointOnSM2Curve(String hexPoint) {
        try {
            // 移除04前缀
            if (!hexPoint.startsWith("04") || hexPoint.length() != 130) {
                return false;
            }

            // 提取x和y坐标
            String xHex = hexPoint.substring(2, 66); // 64字符
            String yHex = hexPoint.substring(66, 130); // 64字符

            BigInteger x = new BigInteger(xHex, 16);
            BigInteger y = new BigInteger(yHex, 16);

            // 验证坐标在有效范围内
            if (x.compareTo(BigInteger.ZERO) < 0 || x.compareTo(SM2_P) >= 0) {
                return false;
            }
            if (y.compareTo(BigInteger.ZERO) < 0 || y.compareTo(SM2_P) >= 0) {
                return false;
            }

            // 计算左边: y²
            BigInteger leftSide = y.modPow(BigInteger.valueOf(2), SM2_P);

            // 计算右边: x³ + ax + b
            BigInteger x3 = x.modPow(BigInteger.valueOf(3), SM2_P);
            BigInteger ax = SM2_A.multiply(x).mod(SM2_P);
            BigInteger rightSide = x3.add(ax).add(SM2_B).mod(SM2_P);

            // 验证方程
            return leftSide.equals(rightSide);

        } catch (Exception e) {
            // 任何解析错误都返回false
            return false;
        }
    }

    /**
     * 检查字符串是否为有效的十六进制字符串
     * 
     * @param str 待检查的字符串
     * @return true 如果是有效的十六进制字符串
     */
    private static boolean isHexString(String str) {
        if (str == null || str.isEmpty()) {
            return false;
        }
        return str.matches("^[0-9a-fA-F]+$");
    }

    /**
     * 验证密钥域（用于SSCL算法）
     * 
     * @param keyDomain 密钥域
     * @throws KeyValidationException 验证失败时抛出
     */
    public static void validateKeyDomain(String keyDomain) {
        if (keyDomain == null || keyDomain.isEmpty()) {
            throw KeyValidationException.invalidFormat("密钥域", "不能为空");
        }
        // 可以根据具体需求添加更多验证规则
    }
}
