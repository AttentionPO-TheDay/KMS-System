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
}
