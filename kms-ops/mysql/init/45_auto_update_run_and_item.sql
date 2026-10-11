SET NAMES utf8mb4;
-- KMS-019：自动更新（托管轮换）任务的两张记录表。
--
-- 为什么必须新建表，而不是继续靠 key_operation_record
-- --------------------------------------------------
-- 改造前 AutoUpdateTask.executeAutoUpdate() 的失败只有一行 log.warn：
--   * KYBER/FALCON 密钥被打开 auto_update 后，rotateKey 必抛异常且 @Transactional
--     回滚 → upd_time 不推进 → 候选 SQL（auto_update='1' AND status!='3'
--     AND upd_time<=cutoff）每轮仍命中它 —— 每 60s 一条 warn，永不成功；
--   * 「本轮跑了没有 / 成功几条 / 失败几条 / 为什么失败」任何地方都查不到。
-- key_operation_record 补不了这个缺口：它**没有轮次维度**，且"提交前就失败"
-- 的候选（KYBER/FALCON、已回收）在那张表里根本没有行 —— 那正是最需要
-- 被看见的一类失败。
--
-- 两张表的分工
-- ------------
--   kms_auto_update_run   一轮扫描一条（任务级：候选/成功/失败/跳过 + 起止时间）
--   kms_auto_update_item  一个候选一条（逐密钥：结果/原因/版本跃迁）
--
-- ⚠️ skipped_count 的口径（不许含糊）
-- --------------------------------
-- 它 = countAutoUpdateEnabled()（auto_update='1' 且未回收） − candidate_count
--   = 「开着开关、但还没到 interval-minutes 窗口」的密钥数。
-- 它**不是**"全部密钥里被跳过的部分"，也不是错误 —— 页面文案必须照此解释，
-- 否则会读成"有这么多个失败被吞了"。
--
-- 幂等：本文件用 CREATE TABLE IF NOT EXISTS，可重复执行。

CREATE TABLE IF NOT EXISTS kms_auto_update_run (
    run_id          VARCHAR(36) NOT NULL COMMENT 'run id (uuid)',
    trigger_source  VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED' COMMENT 'trigger source SCHEDULED / MANUAL',
    started_at      DATETIME    NOT NULL COMMENT 'run start time',
    finished_at     DATETIME    DEFAULT NULL COMMENT 'run finish time',
    candidate_count INT         NOT NULL DEFAULT 0 COMMENT 'due candidates this round (auto_update=1 and upd_time<=cutoff)',
    success_count   INT         NOT NULL DEFAULT 0 COMMENT 'candidates whose rotation was submitted successfully',
    fail_count      INT         NOT NULL DEFAULT 0 COMMENT 'candidates whose rotation threw (reason in item)',
    skipped_count   INT         NOT NULL DEFAULT 0 COMMENT 'enabled-but-not-due keys (countAutoUpdateEnabled - candidate_count)',
    create_time     DATETIME    DEFAULT NULL COMMENT 'create time',
    PRIMARY KEY (run_id),
    KEY idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='auto update task run (one row per scan round)';

CREATE TABLE IF NOT EXISTS kms_auto_update_item (
    item_id      BIGINT(20)   NOT NULL AUTO_INCREMENT COMMENT 'item id',
    run_id       VARCHAR(36)  NOT NULL COMMENT 'run id',
    key_id       INT          NOT NULL COMMENT 'key id (kms.keymanage.key_id)',
    user_id      BIGINT(20)   DEFAULT NULL COMMENT 'key owner id, denormalized for per-user filtering',
    user_name    VARCHAR(100) DEFAULT NULL COMMENT 'key owner name',
    key_name     VARCHAR(100) DEFAULT NULL COMMENT 'key name',
    encryt_name  VARCHAR(100) DEFAULT NULL COMMENT 'algorithm name',
    result       VARCHAR(16)  NOT NULL COMMENT 'SUCCESS / FAILED',
    reason       VARCHAR(500) DEFAULT NULL COMMENT 'failure reason (exception message, verbatim)',
    from_version INT          DEFAULT NULL COMMENT 'key version before rotation',
    to_version   INT          DEFAULT NULL COMMENT 'key version after rotation (SUCCESS only)',
    updated_at   DATETIME     DEFAULT NULL COMMENT 'when this item was written',
    create_time  DATETIME     DEFAULT NULL COMMENT 'create time',
    PRIMARY KEY (item_id),
    KEY idx_run_id (run_id),
    KEY idx_key_id (key_id),
    KEY idx_user_id (user_id),
    KEY idx_result (result)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='auto update task item (one row per candidate key)';