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
 * <h2>KMS-014 追加的三个会话类事件（计划 §6 第 329 行、§7 阶段 6）</h2>
 * <pre>
 *   ENVELOPE_VERIFIED   接收方验签通过（会话推进到 recipient_verified）
 *   SESSION_ESTABLISHED 会话建立（双方 proof 一致）
 *   SESSION_CLOSED      会话关闭（终态）
 * </pre>
 * 计划要求的七个事件至此齐备（前四个由 KMS-006/007/008 接通）。
 * 三者的锚定口径与 {@code KEY_DISTRIBUTED} 一致：{@code keyId} 是
 * **被用于建立会话的那把长期密钥**（新流程 = 接收方那一行）的整数主键，
 * nodeId 是该密钥的归属节点 —— 链上回读时要能回答"谁的哪把钥匙受了影响"。
 *
 * <p>⚠️ 这三个事件是**只留痕、不改状态**：`UpdatedelChainConsumer` 对它们
 * 只记一条 info（与 KEY_DISTRIBUTED 同口径）。会话状态由 PQKDS 侧的状态机
 * 负责，让链上消费者也去改状态会造出第二套事实来源。
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
    /** KMS-014：接收方验签通过（会话推进到 recipient_verified）。 */
    public static final String TYPE_ENVELOPE_VERIFIED = "ENVELOPE_VERIFIED";
    /** KMS-014：会话建立（双方 proof 一致，established）。 */
    public static final String TYPE_SESSION_ESTABLISHED = "SESSION_ESTABLISHED";
    /** KMS-014：会话关闭（终态）。 */
    public static final String TYPE_SESSION_CLOSED = "SESSION_CLOSED";
    /** 任务书「节点多级授权」：授权申请被批准（双向放行）。 */
    public static final String TYPE_AUTH_GRANTED = "AUTH_GRANTED";
    /** 任务书「节点多级授权」：授权申请被驳回（未授予任何权限）。 */
    public static final String TYPE_AUTH_REJECTED = "AUTH_REJECTED";

    /**
     * KMS-014：只留痕、不改状态的会话类事件集合。
     *
     * <p>放在类里而不是消费端各写一遍：发布侧的白名单、消费侧的忽略分支、
     * 以及文档三处都要用同一个集合 —— 分头写必然漂移，而漂移的表现是
     * "某个事件在链上有、状态却被误改"或"事件被当错误重试"。
     */
    public static final java.util.Set<String> SESSION_TRAIL_ONLY_TYPES =
        java.util.Collections.unmodifiableSet(new java.util.LinkedHashSet<>(java.util.Arrays.asList(
            TYPE_ENVELOPE_VERIFIED, TYPE_SESSION_ESTABLISHED, TYPE_SESSION_CLOSED)));

    /**
     * 「节点多级授权」的两个事件：也只留痕、不改状态。
     *
     * <p>与 {@link #SESSION_TRAIL_ONLY_TYPES} <b>分开命名</b>而不是塞进那个集合：
     * 那个名字是"会话类"，把授权事件混进去会让注释说谎 —— 本仓库对
     * 「名字与内容不符」是明确拒绝的（历史上有过文件名与内容不符的坑）。
     * 消费端两处都判，见 {@code UpdatedelChainConsumer}。
     *
     * <h2>⚠️ keyId 位的边界（链上读者必读）</h2>
     * 这两个事件**没有对应的密钥**：授权发生在两个节点之间，不涉及任何一把
     * 长期密钥。链上契约的 {@code keyId} 是 uint256、必须给整数，所以这里装的是
     * **授权申请单的整数主键**（{@code NodeAuthorizationRequest.pk}）。
     *
     * <p>由此推出三条约束：
     * <ol>
     *   <li>该整数与 {@code NodeLongTermKey.pk} / {@code keymanage.key_id}
     *       <b>不是同一个 id 空间</b>，数值会重叠 —— 任何按 keyId 回查密钥表的
     *       读者，必须<b>先按 eventType 分支</b>再解释 keyId；</li>
     *   <li>这两个事件<b>不得</b>进入任何"按 keyId 反查受影响密钥/会话/池项"的
     *       分析（泄漏分析、密钥健康度）—— 那会静默串到无关的密钥上；</li>
     *   <li>单条事件只锚定"某张申请单被批准/驳回"这一个事实，<b>不含两个方向</b>。
     *       双向效果由 DB 的两行授权 + 审批响应里的 {@code granted} 表达；
     *       不接受"把两个方向编进 publicMaterialHash"这种扩展。</li>
     * </ol>
     */
    public static final java.util.Set<String> AUTH_TRAIL_ONLY_TYPES =
        java.util.Collections.unmodifiableSet(new java.util.LinkedHashSet<>(java.util.Arrays.asList(
            TYPE_AUTH_GRANTED, TYPE_AUTH_REJECTED)));

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
     * <p>认不出的值**原样返回**（大写化后），不强行归到某一类：把一个未知
     * 事件硬塞进"更新"或"回收"，会让审计记录说谎。宁可让上层看到陌生值，
     * 也不要给它一个错误的定性。
     *
     * <p>KMS-014 的七个规范值（四个密钥事件 + 三个会话事件）本来就按规范
     * 拼写发布，走 default 分支原样返回 —— 只有两个历史值需要真正改写。
     * 白名单判定在 {@code InternalLifecycleController} 的入口处显式枚举，
     * 那里才是"哪些值被接受"的单一出处。
     */
    public static String normalize(String raw) {
        if (raw == null) {
            return null;
        }
        String value = raw.trim().toUpperCase();
        switch (value) {
            case TYPE_ROTATE:
                return TYPE_KEY_UPDATED;
            case TYPE_REVOKE:
                return TYPE_KEY_REVOKED;
            default:
                return value;
        }
    }

    private String actionType;
    private List<Keymanage> keyList;

    public List<Keymanage> getKeys() {
        return keyList;
    }
}