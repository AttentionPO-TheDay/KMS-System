-- =============================================================================
-- 23_version_k gc_and_mark_legacy_keys.sql
-- -----------------------------------------------------------------------------
-- 目的：让 `ms` 轮换**不再破坏历史可审计性**，并给存量旧密钥一个明确的状态。
--
-- 背景
-- ----
-- `ms`（KGC 主私钥）是 PPub / SSCL 域份额 / 链上公钥 `P_A = W_A + λ·ms·G` 的共同种子。
-- 它一换，用旧 ms 算出的历史 `P_A` 就再也复算不出来 —— 链上存证随之失去可验证性。
--
-- 上一轮安全加固把 ms 从"硬编码公开值"轮换成了真实随机值，因此需要：
--   1. 把**旧 ms 保留为 ms_v1**（退役但可查），新 ms 记为 **ms_v2**（启用）；
--   2. 给每条密钥记录标明它由哪一版签发（`ms_key_id`），
--      复算历史 `P_A` 时按记录里的版本取密钥 → **历史记录始终可复算**；
--   3. 同时记录算法参数版本（`algorithm_version`）与材料可用状态（`key_material_state`）。
--
-- 关于 `key_material_state = legacy_unusable`
-- ----------------------------------------
-- 早期密钥的用户侧本地份额 `u` **从未持久化**（浏览器每次刷新页面重新生成），
-- 若用户当年也没有自行保存 `d_A`，这把密钥从解密角度已经不可用。
-- **这不是故障，而是密钥隔离设计生效的表现** —— 服务端若能自行恢复 `d_A`，
-- 反而说明"用户私钥不出客户端"这条不变量失效了。因此不尝试恢复，只如实标记。
-- P3 的端到端测试必须排除这些记录，改用新登记的密钥。
--
-- 幂等：全部为 ADD COLUMN IF NOT EXISTS 语义（MySQL 8 无此语法，用 information_schema 判断）
--       与带 WHERE 条件的 UPDATE，可重复执行。
-- =============================================================================

SET @db := DATABASE();

-- ---------------------------------------------------------------------------
-- 1. 新增三列
-- ---------------------------------------------------------------------------
SET @sql := (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'keymanage' AND COLUMN_NAME = 'ms_key_id') = 0,
  'ALTER TABLE keymanage ADD COLUMN ms_key_id VARCHAR(32) NULL COMMENT ''签发本记录的 KGC 主私钥版本（如 ms_v1 / ms_v2），用于按版本复算历史 P_A''',
  'SELECT ''ms_key_id 已存在，跳过'''));
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'keymanage' AND COLUMN_NAME = 'algorithm_version') = 0,
  'ALTER TABLE keymanage ADD COLUMN algorithm_version VARCHAR(48) NULL COMMENT ''算法参数版本；v0_random_sscl_domain=域参数每进程随机（旧）， v1_derived_sscl_domain=由 ms 确定性派生''',
  'SELECT ''algorithm_version 已存在，跳过'''));
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'keymanage' AND COLUMN_NAME = 'key_material_state') = 0,
  'ALTER TABLE keymanage ADD COLUMN key_material_state VARCHAR(24) NOT NULL DEFAULT ''active'' COMMENT ''active=可用于解密；legacy_unusable=早期密钥，用户侧份额已丢失，不尝试恢复''',
  'SELECT ''key_material_state 已存在，跳过'''));
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 2. 回填：所有**已存在**的记录都是 ms_v1 + v0 随机域参数签发的
-- ---------------------------------------------------------------------------
-- 只回填还没标过的行（ms_key_id IS NULL），这样重复执行不会覆盖新记录。
-- 注意：这个 UPDATE 必须在本次迁移中先于任何新记录产生 —— 它按"字段为空"判定，
--       所以即使之后又有新数据（会带 ms_v2/v1）也不会被误伤。
UPDATE keymanage
SET ms_key_id          = 'ms_v1',
    algorithm_version  = COALESCE(algorithm_version, 'v0_random_sscl_domain'),
    key_material_state = 'legacy_unusable'
WHERE ms_key_id IS NULL;

-- ---------------------------------------------------------------------------
-- 3. 自检
-- ---------------------------------------------------------------------------
SELECT '未标注版本的历史记录（应为 0）' AS check_item, COUNT(*) AS actual
FROM keymanage WHERE ms_key_id IS NULL;

SELECT ms_key_id, algorithm_version, key_material_state, COUNT(*) AS n
FROM keymanage GROUP BY 1, 2, 3 ORDER BY 1, 2;

SELECT '仍标记为可解密的历史密钥（应为 0）' AS check_item, COUNT(*) AS actual
FROM keymanage WHERE ms_key_id = 'ms_v1' AND key_material_state = 'active';
