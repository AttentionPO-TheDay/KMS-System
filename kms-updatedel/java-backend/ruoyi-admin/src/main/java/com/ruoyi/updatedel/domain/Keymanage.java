package com.ruoyi.updatedel.domain;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class Keymanage {
    @JsonProperty("key_id")
    @JsonAlias("keyId")
    private Long keyId;

    @JsonProperty("user_id")
    @JsonAlias("userId")
    private Long userId;

    @JsonProperty("user_name")
    @JsonAlias("userName")
    private String userName;

    @JsonProperty("ua")
    private String ua;

    @JsonProperty("encryt_type")
    @JsonAlias("encrytType")
    private String encrytType;

    @JsonProperty("encryt_name")
    @JsonAlias("encrytName")
    private String encrytName;

    @JsonProperty("key_name")
    @JsonAlias("keyName")
    private String keyName;

    @JsonProperty("key_use")
    @JsonAlias("keyUse")
    private String keyUse;

    @JsonProperty("key_value")
    @JsonAlias("keyValue")
    private String keyValue;

    @JsonProperty("cre_time")
    @JsonAlias("creTime")
    private String creTime;

    @JsonProperty("upd_time")
    @JsonAlias("updTime")
    private String updTime;

    @JsonProperty("auto_update")
    @JsonAlias("autoUpdate")
    private String autoUpdate;

    @JsonProperty("status")
    private String status;

    @JsonProperty("version")
    private Integer version;

    @JsonProperty("chain_hash")
    @JsonAlias("chainHash")
    private String chainHash;

    @JsonProperty("block_height")
    @JsonAlias("blockHeight")
    private Long blockHeight;

    @JsonProperty("chain_status")
    @JsonAlias("chainStatus")
    private String chainStatus;

    @JsonProperty("key_domain")
    @JsonAlias("keyDomain")
    private String keyDomain;

    @JsonProperty("batch_id")
    @JsonAlias("batchId")
    private String batchId;

    @JsonProperty("parent_batch_id")
    @JsonAlias("parentBatchId")
    private String parentBatchId;

    @JsonProperty("root_batch_id")
    @JsonAlias("rootBatchId")
    private String rootBatchId;

    @JsonProperty("tree_path")
    @JsonAlias("treePath")
    private String treePath;

    @JsonProperty("tree_level")
    @JsonAlias("treeLevel")
    private Integer treeLevel;

    @JsonProperty("node_index")
    @JsonAlias("nodeIndex")
    private Integer nodeIndex;

    @JsonProperty("expected_count")
    @JsonAlias("expectedCount")
    private Integer expectedCount;

    @JsonProperty("tree_fanout")
    @JsonAlias("treeFanout")
    private Integer treeFanout;

    @JsonProperty("proof_mode")
    @JsonAlias("proofMode")
    private String proofMode;

    @JsonProperty("commitment_seed")
    @JsonAlias("commitmentSeed")
    private String commitmentSeed;

    @JsonProperty("commitment")
    private String commitment;

    @JsonProperty("consistency_hash")
    @JsonAlias("consistencyHash")
    private String consistencyHash;

    @JsonProperty("batch_root")
    @JsonAlias("batchRoot")
    private String batchRoot;

    @JsonProperty("verify_status")
    @JsonAlias("verifyStatus")
    private String verifyStatus;

    @JsonProperty("verify_message")
    @JsonAlias("verifyMessage")
    private String verifyMessage;

    /**
     * 本记录的密钥材料由哪一版 KGC 主私钥（ms）签发，例如 {@code ms_v1} / {@code ms_v2}。
     *
     * <p>用于**按版本复算历史 P_A**：轮换 ms 后，用新 ms 算出来的 P_A 与链上旧存证
     * 必然不一致；只有按记录自己那一版去取 ms，历史记录才保持可验证。
     * 详见 {@link com.ruoyi.common.crypto.KgcMasterSecret}。
     *
     * <p>为空表示早期记录 —— 它们都是 {@code ms_v1} 签发的。
     */
    @JsonProperty("ms_key_id")
    @JsonAlias("msKeyId")
    private String msKeyId;

    /**
     * 算法参数版本。与 {@link #msKeyId} 正交：同一个 ms 下，算法实现本身也可能换代。
     *
     * <p>当前取值：
     * <ul>
     *   <li>{@code v0_random_sscl_domain} —— 早期版本，SSCL 域参数（多项式与求值点）
     *       是每进程随机生成的，因此**不同进程算出的域参数互不相同**，
     *       那些密钥在客户端插值不出来，已标记为不可用于解密；</li>
     *   <li>{@code v1_derived_sscl_domain} —— 域参数改为从 ms 确定性派生，
     *       可跨进程、跨实现复现。</li>
     * </ul>
     */
    @JsonProperty("algorithm_version")
    @JsonAlias("algorithmVersion")
    private String algorithmVersion;

    /**
     * 密钥材料是否仍**可用于解密**。
     *
     * <p>取值：
     * <ul>
     *   <li>{@code active} —— 正常可用；</li>
     *   <li>{@code legacy_unusable} —— 早期密钥：用户侧本地份额 {@code u} 从未持久化，
     *       若用户当年也没有自己保存 {@code d_A}，这把密钥从解密角度已经不可用。
     *       **这不是故障，而是密钥隔离设计生效的表现** ——
     *       服务端能自己恢复 {@code d_A} 才说明隔离失效了。</li>
     * </ul>
     * P3 的端到端测试必须排除 {@code legacy_unusable} 的记录，只用新登记的密钥。
     */
    @JsonProperty("key_material_state")
    @JsonAlias("keyMaterialState")
    private String keyMaterialState;
}
