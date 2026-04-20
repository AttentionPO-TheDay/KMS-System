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
}
