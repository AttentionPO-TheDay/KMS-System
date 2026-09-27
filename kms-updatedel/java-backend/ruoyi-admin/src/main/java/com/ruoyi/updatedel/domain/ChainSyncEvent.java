package com.ruoyi.updatedel.domain;

import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 链上存证事件。
 *
 * <h2>事件类型统一（阶段 7 / 文档 §8.6）</h2>
 * 文档要求记录四类生命周期事件：
 * <pre>
 *   KEY_CREATED      密钥创建
 *   KEY_UPDATED      密钥更新（轮换）
 *   KEY_REVOKED      密钥回收
 *   KEY_DISTRIBUTED  密钥分发
 * </pre>
 *
 * <p>原先只有 {@code ROTATE} / {@code REVOKE} 两个值，且**创建根本没有事件** ——
 * 于是"这把密钥什么时候产生的"在链上查不到，而那是审计最基本的追问。
 *
 * <h2>为什么保留旧值</h2>
 * {@link #TYPE_ROTATE} / {@link #TYPE_REVOKE} 仍留在类里：历史事件可能已经
 * 按旧值落库或投递，消费端要能认出它们。新的发布一律用新值，
 * 两者通过 {@link #normalize(String)} 归一到同一语义。
 *
 * <h2>上链内容边界（文档 §8.6 明确禁止项）</h2>
 * 事件只携带**公开量与元数据**。绝不携带：
 * <ul>
 *   <li>用户侧秘密份额 {@code u}（本系统从不持久化它，更不该上链）</li>
 *   <li>完整私钥 {@code d_A}</li>
 *   <li>SM4 明文对称密钥</li>
 * </ul>
 * 链上需要的是"发生过什么、对应哪个版本的哪份公开材料"，
 * 而不是能拿来解密的东西。
 */
@Data
@AllArgsConstructor
@NoArgsConstructor
public class ChainSyncEvent {

    // ------------------------------------------------------------------
    // 规范事件类型（阶段 7 §8.6）
    // ------------------------------------------------------------------
    /** 密钥创建。 */
    public static final String TYPE_KEY_CREATED = "KEY_CREATED";
    /** 密钥更新（轮换：key_id 不变、version +1）。 */
    public static final String TYPE_KEY_UPDATED = "KEY_UPDATED";
    /** 密钥回收（终态，不可恢复）。 */
    public static final String TYPE_KEY_REVOKED = "KEY_REVOKED";
    /** 密钥分发（由分发模块产生的事件，经本类型统一命名）。 */
    public static final String TYPE_KEY_DISTRIBUTED = "KEY_DISTRIBUTED";

    // ------------------------------------------------------------------
    // 历史值（只读兼容，不再产生）
    // ------------------------------------------------------------------
    /**
     * @deprecated 历史值，语义等同 {@link #TYPE_KEY_UPDATED}。
     *             保留以便消费端认出按旧值投递过的事件。
     */
    @Deprecated
    public static final String TYPE_ROTATE = "ROTATE";

    /**
     * @deprecated 历史值，语义等同 {@link #TYPE_KEY_REVOKED}。
     */
    @Deprecated
    public static final String TYPE_REVOKE = "REVOKE";

    /**
     * 把任意（含历史）事件类型归一到规范值。
     *
     * <p>认不出的值**原样返回**，不强行归到某一类：把一个未知事件
     * 硬塞进"更新"或"回收"，会让审计记录说谎。宁可让上层看到陌生值，
     * 也不要给它一个错误的定性。
     */
    public static String normalize(String raw) {
        if (raw == null) {
            return null;
        }
        switch (raw.trim().toUpperCase()) {
            case TYPE_ROTATE:
                return TYPE_KEY_UPDATED;
            case TYPE_REVOKE:
                return TYPE_KEY_REVOKED;
            default:
                return raw.trim().toUpperCase();
        }
    }

    private String actionType;
    private List<Keymanage> keyList;

    public List<Keymanage> getKeys() {
        return keyList;
    }
}