package com.ruoyi.updatedel.domain;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class KeyPayload {
    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("action_type")
    private String actionType;

    @JsonProperty("raw_user")
    private String rawUser;

    @JsonProperty("raw_password")
    private String rawPassword;

    @JsonProperty("key_id")
    private Long keyId;

    @JsonProperty("key_info")
    private Keymanage keyInfo;

    @JsonProperty("batch_id")
    private String batchId;

    @JsonProperty("parent_batch_id")
    private String parentBatchId;

    @JsonProperty("root_batch_id")
    private String rootBatchId;

    @JsonProperty("tree_path")
    private String treePath;

    @JsonProperty("tree_level")
    private Integer treeLevel;

    @JsonProperty("node_index")
    private Integer nodeIndex;

    @JsonProperty("expected_count")
    private Integer expectedCount;

    @JsonProperty("tree_fanout")
    private Integer treeFanout;

    @JsonProperty("proof_mode")
    private String proofMode;

    @JsonProperty("commitment_seed")
    private String commitmentSeed;
}
