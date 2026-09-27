package com.ruoyi.generate.domain;

import com.alibaba.fastjson2.annotation.JSONField;

/**
 * 对应 Go 端的 KeyEnrollPayload 结构。
 *
 * <p>原先这里还有一个 {@code raw_password} 字段。它已被移除：生产端（Go）不再投递它，
 * 消费端也从未使用它 —— 留着一个"能把明文口令接进来"的字段本身就是隐患。
 * 历史遗留消息里多出的该字段会被序列化框架忽略，不影响消费。
 */
public class KeyPayload {

    @JSONField(name = "raw_user")
    private String rawUser;

    @JSONField(name = "action_type")
    private String actionType;

    @JSONField(name = "generated_key")
    private Keymanage generatedKey;

    public String getRawUser() { return rawUser; }
    public void setRawUser(String rawUser) { this.rawUser = rawUser; }

    public String getActionType() { return actionType; }
    public void setActionType(String actionType) { this.actionType = actionType; }

    public Keymanage getGeneratedKey() { return generatedKey; }
    public void setGeneratedKey(Keymanage generatedKey) { this.generatedKey = generatedKey; }
}
