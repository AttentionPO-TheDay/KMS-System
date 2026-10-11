SET NAMES utf8mb4;
-- KMS-022：批量一致性检查（用户密钥侧）的两张表。
--
-- 为什么必须落库，而不是每次现算
-- ----------------------------
--   * 改造前只有单钥视角 `GET /lifecycle/keymanage/health/{keyId}`
--     （KeyHealthService，阶段 7）：一次一把，没有"这一批扫了哪些、结果各是什么"；
--   * 「哪些钥有问题、什么问题」是运维要回答的问题，答案必须**可回看** ——
--     现算的结果不留痕，两次扫描之间密钥被修好/改坏就无从对比；
--   * 扫描是**只读**操作：它不改任何密钥状态，只记录判定结果。因此这里的
--     run/item 不是"处置记录"，处置仍走各密钥自己的更新/回收接口。
--
-- 与节点长期密钥侧的分工（E4 拍板）
-- --------------------------------
--   节点长期密钥的健康走 Python 侧既有巡检（NodeKeyInspection + 自动回收服务），
--   本任务**不重复实现**、也不新增扫描端点 —— 管理端页面只读展示它的现状
--   （/node-key-reviews/ 的 review/revoked 两态 + latestBatch）。
--   这就是"两张表只覆盖用户密钥"的原因，不是遗漏。
--
-- 幂等：CREATE TABLE IF NOT EXISTS。

CREATE TABLE IF NOT EXISTS key_health_scan_run (
    run_id        VARCHAR(36) NOT NULL COMMENT 'run id (uuid)',
    user_id       BIGINT(20)  DEFAULT NULL COMMENT 'scope owner: non-null = only this user''s keys; null = all users',
    scope         VARCHAR(16) NOT NULL DEFAULT 'ALL' COMMENT 'scope ALL / OWNER',
    started_at    DATETIME    NOT NULL COMMENT 'scan start time',
    finished_at   DATETIME    DEFAULT NULL COMMENT 'scan finish time',
    total         INT         NOT NULL DEFAULT 0 COMMENT 'keys scanned in this run',
    ok_count      INT         NOT NULL DEFAULT 0 COMMENT 'verdict OK',
    warn_count    INT         NOT NULL DEFAULT 0 COMMENT 'verdict WARN (findings with severity WARN)',
    error_count   INT         NOT NULL DEFAULT 0 COMMENT 'verdict ERROR (findings with severity ERROR)',
    note          VARCHAR(255) DEFAULT NULL COMMENT 'honest remarks (e.g. reached the per-run cap; keys left unscanned)',
    create_time   DATETIME    DEFAULT NULL COMMENT 'create time',
    PRIMARY KEY (run_id),
    KEY idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='key health batch scan run (user keys)';

CREATE TABLE IF NOT EXISTS key_health_scan_item (
    item_id      BIGINT(20)   NOT NULL AUTO_INCREMENT COMMENT 'item id',
    run_id       VARCHAR(36)  NOT NULL COMMENT 'run id',
    key_id       INT          NOT NULL COMMENT 'key id (kms.keymanage.key_id)',
    user_id      BIGINT(20)   DEFAULT NULL COMMENT 'key owner id (denormalized, same discipline as key_operation_record)',
    user_name    VARCHAR(100) DEFAULT NULL COMMENT 'key owner name',
    key_name     VARCHAR(100) DEFAULT NULL COMMENT 'key name',
    encryt_name  VARCHAR(100) DEFAULT NULL COMMENT 'algorithm name',
    key_version  INT          DEFAULT NULL COMMENT 'key version at scan time',
    verdict      VARCHAR(16)  NOT NULL COMMENT 'OK / WARN / ERROR',
    rule         VARCHAR(255) DEFAULT NULL COMMENT 'comma-joined finding rules (empty for OK)',
    summary      VARCHAR(500) DEFAULT NULL COMMENT 'finding messages joined, or the honest "no findings" text',
    create_time  DATETIME     DEFAULT NULL COMMENT 'create time',
    PRIMARY KEY (item_id),
    KEY idx_run_id (run_id),
    KEY idx_key_id (key_id),
    KEY idx_user_id (user_id),
    KEY idx_verdict (verdict)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='key health batch scan item (one row per scanned key)';