package com.ruoyi.updatedel.domain;

import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class ChainSyncEvent {
    public static final String TYPE_ROTATE = "ROTATE";
    public static final String TYPE_REVOKE = "REVOKE";

    private String actionType;
    private List<Keymanage> keyList;
}
