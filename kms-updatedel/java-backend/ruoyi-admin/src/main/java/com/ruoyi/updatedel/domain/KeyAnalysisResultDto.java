package com.ruoyi.updatedel.domain;

import lombok.Data;
import java.util.List;
import java.util.Map;

@Data
public class KeyAnalysisResultDto {
    /**
     * 嫌疑密钥基准信息
     */
    private Keymanage baseInfo;

    /**
     * 分发足迹（持有改密钥的其他业务节点/用户）
     */
    private List<Map<String, Object>> distributeFootprints;

    /**
     * 历史操作轨迹（谁碰过它）
     */
    private List<Map<String, Object>> operationTrails;
}
