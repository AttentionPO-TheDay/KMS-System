package com.ruoyi.generate.domain;

import java.io.Serializable;
import java.util.List;

/**
 * 区块链异步同步事件包
 */
public class ChainSyncEvent implements Serializable {

    public static final String TYPE_ENROLL = "ENROLL";
    public static final String TYPE_REVOKE = "REVOKE";
    public static final String TYPE_ROTATE = "ROTATE";
    public static final String TYPE_FREEZE = "FREEZE";

    private String actionType;
    private List<Keymanage> keys;

    public ChainSyncEvent() {}

    public ChainSyncEvent(String actionType, List<Keymanage> keys) {
        this.actionType = actionType;
        this.keys = keys;
    }

    public String getActionType() { return actionType; }
    public void setActionType(String actionType) { this.actionType = actionType; }

    public List<Keymanage> getKeys() { return keys; }
    public void setKeys(List<Keymanage> keys) { this.keys = keys; }
}
