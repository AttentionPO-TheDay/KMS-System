package com.ruoyi.generate.domain;

/**
 * 密钥状态枚举
 */
public enum KeyStatus {

    ACTIVE("0", "正常", 0),
    FROZEN("1", "已冻结", 1),
    ROTATED("2", "已轮换", 2),
    REVOKED("3", "已回收", 3);

    private final String code;
    private final String info;
    private final int contractVal;

    KeyStatus(String code, String info, int contractVal) {
        this.code = code;
        this.info = info;
        this.contractVal = contractVal;
    }

    public String getCode() { return code; }
    public String getInfo() { return info; }
    public int getContractVal() { return contractVal; }

    public static KeyStatus getByCode(String code) {
        for (KeyStatus value : values()) {
            if (value.getCode().equals(code)) {
                return value;
            }
        }
        return null;
    }
}
