package com.ruoyi.common.crypto;

/**
 * 密钥材料的**版本标记**常量。
 *
 * <p>每条密钥记录都会写明两件事，二者正交：
 * <ol>
 *   <li>{@link #MS_V1} / {@link #MS_V2}… —— 由哪一版 KGC 主私钥 {@code ms} 签发
 *       （存在 {@code keymanage.ms_key_id}）。用于**按版本复算历史 P_A**：
 *       轮换 {@code ms} 后必须按记录自己那一版取密钥，否则链上旧存证会失去可验证性。
 *       见 {@link KgcMasterSecret}。</li>
 *   <li>{@link #ALGORITHM_V1_DERIVED} / {@link #ALGORITHM_V0_RANDOM} —— 算法参数版本
 *       （存在 {@code keymanage.algorithm_version}）。同一个 {@code ms} 下，
 *       算法实现本身也可能换代。</li>
 * </ol>
 *
 * <p>把这些字面量集中在这里，是为了避免"两处各写一份字符串、改一处漏一处" ——
 * 那类漂移在版本判定上会直接导致历史记录判错版本。
 */
public final class KeyMaterialEpoch {

    /** 早期的 KGC 主私钥版本。它是那个**公开的演示值**，现已退役，仅用于历史复算。 */
    public static final String MS_V1 = "ms_v1";

    /** 当前的 KGC 主私钥版本（真实随机值）。 */
    public static final String MS_V2 = "ms_v2";

    /**
     * 算法参数版本：**旧**。SSCL 的域参数（多项式系数与求值点）当时是
     * 每个进程启动时随机生成的，因此不同进程算出的域参数互不相同 ——
     * 客户端拿 `/comparam` 的点去插值，结果与密钥里存的 {@code SSCLEA} 对不上。
     * 这类记录一律标记为不可用于解密。
     */
    public static final String ALGORITHM_V0_RANDOM = "v0_random_sscl_domain";

    /**
     * 算法参数版本：**当前**。SSCL 域参数改为从 {@code ms} 用 SM3 确定性派生，
     * 可跨进程、跨语言复现。
     */
    public static final String ALGORITHM_V1_DERIVED = "v1_derived_sscl_domain";

    /** 材料状态：正常可用。 */
    public static final String STATE_ACTIVE = "active";

    /**
     * 材料状态：早期密钥，**不可用于解密**。
     *
     * <p>原因不是故障，而是密钥隔离设计生效：用户侧本地份额 {@code u} 从未持久化，
     * 用户若也没有自行保存 {@code d_A}，这把密钥就无法再解开任何东西。
     * 服务端若能自行恢复 {@code d_A}，反而说明"用户私钥不出客户端"这条不变量失效了。
     * 因此**不尝试恢复**，只如实标记；P3 的端到端测试排除这类记录。
     */
    public static final String STATE_LEGACY_UNUSABLE = "legacy_unusable";

    private KeyMaterialEpoch() {
    }
}