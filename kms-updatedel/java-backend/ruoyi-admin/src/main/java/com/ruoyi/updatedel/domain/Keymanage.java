package com.ruoyi.updatedel.domain;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class Keymanage {
    @JsonProperty("key_id")
    private Long keyId;

    @JsonProperty("user_id")
    private Long userId;

    @JsonProperty("user_name")
    private String userName;

    @JsonProperty("ua")
    private String ua;

    @JsonProperty("encryt_type")
    private String encrytType;

    @JsonProperty("encryt_name")
    private String encrytName;

    @JsonProperty("key_name")
    private String keyName;

    @JsonProperty("key_use")
    private String keyUse;

    @JsonProperty("key_value")
    private String keyValue;

    @JsonProperty("cre_time")
    private String creTime;

    @JsonProperty("upd_time")
    private String updTime;

    @JsonProperty("auto_update")
    private String autoUpdate;

    @JsonProperty("status")
    private String status;

    @JsonProperty("version")
    private Integer version;

    @JsonProperty("chain_hash")
    private String chainHash;

    @JsonProperty("block_height")
    private Long blockHeight;

    @JsonProperty("chain_status")
    private String chainStatus;

    @JsonProperty("key_domain")
    private String keyDomain;
}
