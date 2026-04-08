package com.ruoyi.keymanage.domain;

import com.alibaba.fastjson2.annotation.JSONField;


/**
 * 对应 Go 端的 KeyPayload 结构
 */
public class KeyPayload {

    @JSONField(name = "raw_user")
    private String rawUser;

    @JSONField(name = "raw_password")
    private String rawPassword;

    @JSONField(name = "action_type")
    private String actionType;

    @JSONField(name = "generated_key")
    private Keymanage generatedKey;

    public String getRawUser() {
        return rawUser;
    }

    public void setRawUser(String rawUser) {
        this.rawUser = rawUser;
    }

    public String getRawPassword() {
        return rawPassword;
    }

    public void setRawPassword(String rawPassword) {
        this.rawPassword = rawPassword;
    }

    public String getActionType() {
        return actionType;
    }

    public void setActionType(String actionType) {
        this.actionType = actionType;
    }

    public Keymanage getGeneratedKey() {
        return generatedKey;
    }

    public void setGeneratedKey(Keymanage generatedKey) {
        this.generatedKey = generatedKey;
    }
}
