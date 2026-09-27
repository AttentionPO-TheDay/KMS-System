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

    /**
     * 阶段 7（文档 §8.3）：依赖这把密钥的**预分配池项**（仍可取用的那些）。
     *
     * <p>泄漏处置时要知道"该失效哪些池项" —— 已消费的是历史事实、不该动，
     * 所以只统计 READY/RESERVED。与 §7.6 的连带失效用的是同一条关联链，
     * 因此这里的结论可直接指导处置。
     */
    private List<Map<String, Object>> affectedPoolItems;

    /**
     * 阶段 7（文档 §8.3）：受影响的节点（本密钥分发到达过哪些节点）。
     *
     * <p>泄露处置时需要通知的对端。附带 permission_level 与 domain_id，
     * 便于判断影响面里有没有高权限节点或跨域节点。
     */
    private List<Map<String, Object>> affectedNodes;
}
