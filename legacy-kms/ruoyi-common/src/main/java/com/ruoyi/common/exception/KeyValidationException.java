package com.ruoyi.common.exception;

/**
 * 密钥验证异常类
 * 用于密钥格式、长度、椭圆曲线点等验证失败时抛出
 * 
 * @author ruoyi
 * @date 2026-01-22
 */
public class KeyValidationException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    /**
     * 错误码
     */
    private Integer code;

    /**
     * 错误明细信息
     */
    private String detailMessage;

    /**
     * 错误码枚举
     */
    public enum ErrorCode {
        INVALID_KEY_LENGTH(4001, "密钥长度不合法"),
        INVALID_CURVE_POINT(4002, "椭圆曲线点不在曲线上"),
        INVALID_KEY_FORMAT(4003, "密钥格式不合法"),
        INVALID_KEY_PREFIX(4004, "密钥前缀不正确"),
        INVALID_CREDENTIALS(4005, "用户凭证格式不合法");

        private final int code;
        private final String message;

        ErrorCode(int code, String message) {
            this.code = code;
            this.message = message;
        }

        public int getCode() {
            return code;
        }

        public String getMessage() {
            return message;
        }
    }

    /**
     * 空构造方法
     */
    public KeyValidationException() {
        super();
    }

    /**
     * 使用消息构造
     * 
     * @param message 错误消息
     */
    public KeyValidationException(String message) {
        super(message);
    }

    /**
     * 使用消息和错误码构造
     * 
     * @param message 错误消息
     * @param code    错误码
     */
    public KeyValidationException(String message, Integer code) {
        super(message);
        this.code = code;
    }

    /**
     * 使用错误码枚举构造
     * 
     * @param errorCode 错误码枚举
     */
    public KeyValidationException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.code = errorCode.getCode();
    }

    /**
     * 使用错误码枚举和详细消息构造
     * 
     * @param errorCode     错误码枚举
     * @param detailMessage 详细错误信息
     */
    public KeyValidationException(ErrorCode errorCode, String detailMessage) {
        super(errorCode.getMessage() + ": " + detailMessage);
        this.code = errorCode.getCode();
        this.detailMessage = detailMessage;
    }

    /**
     * 获取错误码
     */
    public Integer getCode() {
        return code;
    }

    /**
     * 设置错误码
     */
    public void setCode(Integer code) {
        this.code = code;
    }

    /**
     * 获取详细错误信息
     */
    public String getDetailMessage() {
        return detailMessage;
    }

    /**
     * 设置详细错误信息
     */
    public KeyValidationException setDetailMessage(String detailMessage) {
        this.detailMessage = detailMessage;
        return this;
    }

    // 静态工厂方法 - 提供便捷的异常创建

    /**
     * 创建密钥长度异常
     * 
     * @param keyType        密钥类型
     * @param expectedLength 期望长度
     * @param actualLength   实际长度
     * @return KeyValidationException
     */
    public static KeyValidationException invalidLength(String keyType, int expectedLength, int actualLength) {
        String detail = String.format("%s长度应为%d字符，实际为%d字符", keyType, expectedLength, actualLength);
        return new KeyValidationException(ErrorCode.INVALID_KEY_LENGTH, detail);
    }

    /**
     * 创建密钥格式异常
     * 
     * @param keyType 密钥类型
     * @param reason  原因
     * @return KeyValidationException
     */
    public static KeyValidationException invalidFormat(String keyType, String reason) {
        String detail = String.format("%s格式错误: %s", keyType, reason);
        return new KeyValidationException(ErrorCode.INVALID_KEY_FORMAT, detail);
    }

    /**
     * 创建曲线点异常
     * 
     * @param reason 原因
     * @return KeyValidationException
     */
    public static KeyValidationException invalidCurvePoint(String reason) {
        return new KeyValidationException(ErrorCode.INVALID_CURVE_POINT, reason);
    }

    /**
     * 创建密钥前缀异常
     * 
     * @param expectedPrefix 期望前缀
     * @param actualPrefix   实际前缀
     * @return KeyValidationException
     */
    public static KeyValidationException invalidPrefix(String expectedPrefix, String actualPrefix) {
        String detail = String.format("密钥前缀应为'%s'，实际为'%s'", expectedPrefix, actualPrefix);
        return new KeyValidationException(ErrorCode.INVALID_KEY_PREFIX, detail);
    }

    /**
     * 创建用户凭证异常
     * 
     * @param field       字段名
     * @param requirement 要求
     * @return KeyValidationException
     */
    public static KeyValidationException invalidCredentials(String field, String requirement) {
        String detail = String.format("%s不符合要求: %s", field, requirement);
        return new KeyValidationException(ErrorCode.INVALID_CREDENTIALS, detail);
    }
}
