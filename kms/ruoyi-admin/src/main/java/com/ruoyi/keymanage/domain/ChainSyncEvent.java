package com.ruoyi.keymanage.domain;

import java.io.Serializable;
import java.util.List;

/**
 * 区块链异步同步事件包
 */
public class ChainSyncEvent implements Serializable {

    // 操作类型常量
    public static final String TYPE_ENROLL = "ENROLL";   // 新增/生成 (需要计算PA)
    public static final String TYPE_REVOKE = "REVOKE";   // 吊销/删除 (只改状态)
    public static final String TYPE_ROTATE = "ROTATE";   // 轮换/更新 (只改状态或新增)
    public static final String TYPE_FREEZE = "FREEZE";   // 冻结 (只改状态)

    private String actionType;       // 操作标签
    private List<Keymanage> keys;    // 数据负载 (KeyId是必须的)

    // 构造函数
    public ChainSyncEvent() {}

    public ChainSyncEvent(String actionType, List<Keymanage> keys) {
        this.actionType = actionType;
        this.keys = keys;
    }

    // Getter & Setter
    public String getActionType() { return actionType; }
    public void setActionType(String actionType) { this.actionType = actionType; }
    public List<Keymanage> getKeys() { return keys; }
    public void setKeys(List<Keymanage> keys) { this.keys = keys; }
}
