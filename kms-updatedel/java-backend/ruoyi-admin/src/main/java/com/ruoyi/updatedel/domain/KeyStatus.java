package com.ruoyi.updatedel.domain;

public enum KeyStatus {
    ACTIVE("0"),
    FROZEN("1"),
    ROTATED("2"),
    REVOKED("3");

    private final String code;

    KeyStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
