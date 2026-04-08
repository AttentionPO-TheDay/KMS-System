package com.ruoyi.keymanage.domain;

/**
 * 密钥状态枚举
 * 对应数据库 status 字段，以及区块链合约的 uint8 status
 * * 设计逻辑：
 * 1. ACTIVE: 当前正在使用的密钥 (MySQL中通常是这个状态)
 * 2. FROZEN: 管理员暂停使用的密钥
 * 3. ROTATED: 已轮换/过期的旧密钥 (主要出现在区块链历史日志中，或数据库的历史归档表中)
 * 4. REVOKED: 彻底废弃/删除的密钥
 */
public enum KeyStatus {

    /** 正常/使用中 (Active) - 对应版本号最新的密钥 */
    ACTIVE("0", "正常", 0),

    /** 已冻结 (Frozen) - 临时暂停 */
    FROZEN("1", "已冻结", 1),

    /** 已轮换 (Rotated) - 历史版本/旧密钥 (新版本生成后，旧版本变为此状态) */
    ROTATED("2", "已轮换", 2),

    /** 已回收 (Revoked) - 永久吊销/删除 */
    REVOKED("3", "已回收", 3);

    private final String code;      // 对应数据库/Java实体类的 String status
    private final String info;      // 中文描述
    private final int contractVal;  // 对应区块链合约的 uint8 status

    KeyStatus(String code, String info, int contractVal) {
        this.code = code;
        this.info = info;
        this.contractVal = contractVal;
    }

    public String getCode() {
        return code;
    }

    public String getInfo() {
        return info;
    }

    public int getContractVal() {
        return contractVal;
    }

    /**
     * 根据数据库的 String code 获取枚举
     */
    public static KeyStatus getByCode(String code) {
        for (KeyStatus value : values()) {
            if (value.getCode().equals(code)) {
                return value;
            }
        }
        return null;
    }
}