-- =============================================================================
-- 33_key_version_history.sql
-- -----------------------------------------------------------------------------
-- 阶段 4（文档 §5.2）：密钥**版本历史**表。
--
-- 解决的问题
-- ----------
-- `rotateKey` 是**原地 UPDATE**（`keymanageMapper.updatekeymanage(next)`）：
-- 版本号 +1 的同时，旧的 `key_value`（KGC 部分密钥）与 `ua` 被**直接覆盖**，
-- 旧版本材料就此丢失。而文档 §5.2 明确要求：
--     「旧版本不能物理删除，因为历史分发、会话、链上存证和签名验证可能需要它。」
--
-- 现实影响：轮换后无法回答"这把密钥 v1 时的公钥是什么"，也就无法验证
-- 早先签发的分发记录或链上存证是否对应同一把逻辑密钥。
--
-- 做法
-- ----
-- 不改动 `keymanage` 的现有语义（它始终表示**当前版本**），
-- 而是在**轮换覆盖之前**把当前行快照写入本表。这样：
--   * 读当前状态仍是单表查询，既有代码与索引不受影响；
--   * 历史版本按 (key_id, version) 唯一，重复归档是幂等的。
--
-- 为什么不把历史做成 keymanage 的多行（key_id + version 作主键）
-- --------------------------------------------------------------
-- 那需要改主键、改 `key_operation_record` 的引用、改所有按 key_id 取"当前密钥"
-- 的查询，牵动面远超本阶段范围，且会让"按 key_id 查当前密钥"从主键查找
-- 退化成带排序的二级查找。快照表是最小侵入的做法。
--
-- ⚠️ 只存**公钥侧与元数据**：`key_value` 存的是 KGC 部分密钥（服务端本就持有），
--    节点侧的 `u` 从来不在这张表里，也不应该进来。
--
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT ... ON DUPLICATE KEY UPDATE。
-- =============================================================================

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `keymanage_version_history` (
    `history_id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '历史记录ID',
    `key_id`              INT          NOT NULL COMMENT '逻辑密钥ID（对应 keymanage.key_id）',
    `version`             INT          NOT NULL COMMENT '该快照对应的版本号',

    -- 密钥材料的快照（与 keymanage 对应列同宽）
    `ua`                  VARCHAR(1024) DEFAULT NULL COMMENT '用户部分公钥（公开量）',
    `key_value`           VARCHAR(1024) DEFAULT NULL COMMENT 'KGC 部分密钥（服务端持有）',
    `encryt_type`         VARCHAR(255) DEFAULT NULL COMMENT '加密算法类型',
    `encryt_name`         VARCHAR(255) DEFAULT NULL COMMENT '加密算法名称',
    `key_domain`          VARCHAR(255) DEFAULT NULL COMMENT '密钥域',

    -- 状态与版本标记
    `status`              VARCHAR(255) DEFAULT NULL COMMENT '归档时的密钥状态',
    `ms_key_id`           VARCHAR(32)  DEFAULT NULL COMMENT '签发该版本所用的 KGC 主私钥版本',
    `algorithm_version`   VARCHAR(48)  DEFAULT NULL COMMENT '算法参数版本',

    -- 链上存证（历史分发/验证需要）
    `chain_hash`          VARCHAR(100) DEFAULT NULL COMMENT '归档时的链上交易Hash',
    `block_height`        BIGINT       DEFAULT NULL COMMENT '归档时的区块高度',
    `chain_status`        CHAR(1)      DEFAULT NULL COMMENT '归档时的上链状态',

    -- 归档元数据
    `archived_at`         DATETIME     DEFAULT NULL COMMENT '归档时间',
    `archived_reason`     VARCHAR(32)  DEFAULT NULL COMMENT '归档原因：ROTATE / REVOKE',
    `archived_by`         VARCHAR(64)  DEFAULT NULL COMMENT '触发归档的操作来源',

    PRIMARY KEY (`history_id`),
    -- 同一 key_id 的同一版本只归档一次；重复归档走 ON DUPLICATE KEY UPDATE，
    -- 使整个流程可安全重试。
    UNIQUE KEY `uk_key_version` (`key_id`, `version`),
    KEY `idx_key_id` (`key_id`)
) ENGINE=InnoDB COMMENT='密钥版本历史快照（阶段4）';

-- ---------------------------------------------------------------------------
-- 自检
-- ---------------------------------------------------------------------------
SELECT '版本历史表' AS check_item, COLUMN_NAME, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'keymanage_version_history'
ORDER BY ORDINAL_POSITION;

SELECT '历史表行数（新建应为 0）' AS check_item, COUNT(*) AS rows_now
FROM keymanage_version_history;
