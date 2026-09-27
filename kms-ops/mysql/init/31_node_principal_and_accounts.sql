-- =============================================================================
-- 31_node_principal_and_accounts.sql
-- -----------------------------------------------------------------------------
-- 阶段 2（身份模型）kms 侧：引入「登录主体类型」principal_type。
--
-- 背景与目标
-- ----------
-- 文档 §2.1 要求系统至少保留两类身份：
--   ADMIN —— 平台管理员，负责创建/停用节点与系统治理，**不是**普通密钥业务主体
--   NODE  —— 区块链节点，业务使用者（生成/更新/分发/建会话）
--
-- 现状（2026-09-27 核实）：只有 `role_level` 一个字段在承担分流，而它同时被
-- 三个不同概念挤在一起：
--   ① 登录主体类型（管理员 / 普通用户）
--   ② 节点权限等级（L1/L2/L3 多级授权）
--   ③ 业务角色
-- 文档 §2.2 明确要求把这三个概念**拆开**，不要再塞进同一个 role_level。
--
-- 本脚本只做第 ① 项（principal_type）。②的落点在 Node 表（见 Django 迁移
-- 0008_node_principal），③本轮不引入。
--
-- 为什么不删 role_level
-- --------------------
-- `role_level` 目前仍被以下链路读取，删掉会连带打穿：
--   * 前端 `utils/role.js` 的 isAdminLevel()，且**管理端准入判据**就是它
--     （`permission.js` 守卫，阶段 1 实测：普通用户靠它被挡在 /401）
--   * `KeyValueSanitizer` / 生命周期控制器的按属主脱敏与门禁
-- 因此本轮**新增** principal_type 与之并行，role_level 留待阶段 9 统一收口。
-- 两者在过渡期的取值必须保持一致（见下方回填规则），否则会出现
-- "principal_type 说是 NODE、role_level 却放行进管理端"这类自相矛盾的状态。
--
-- 幂等：ADD COLUMN IF NOT EXISTS（MySQL 8.0 不支持该语法，故用
--       information_schema 判存 + PREPARE 动态执行），可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 加列：principal_type
-- ---------------------------------------------------------------------------
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'sys_user'
      AND COLUMN_NAME = 'principal_type'
);
SET @ddl := IF(@col_exists = 0,
    "ALTER TABLE sys_user
       ADD COLUMN principal_type VARCHAR(16) NOT NULL DEFAULT 'NODE'
       COMMENT '登录主体类型：ADMIN=平台管理员 / NODE=区块链节点'
       AFTER role_level",
    'SELECT ''principal_type 已存在，跳过'' AS skip_msg');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 2. 回填：与 role_level 保持一致（过渡期两者不得互相矛盾）
-- ---------------------------------------------------------------------------
-- 规则：role_level <= 0 → ADMIN；其余 → NODE。
-- 这正是前端 `isAdminLevel()` 的判据（见 utils/role.js），保持一致才不会出现
-- "能进管理端但被标成 NODE"这类矛盾态。
--
-- 说明：`yx` / `acceptance_user` / `test01` / `user01` 都是 role_level=2 的
-- 测试账号，回填成 NODE 后行为不变（它们本来就是"业务侧"账号）。
UPDATE sys_user SET principal_type = 'ADMIN' WHERE role_level <= 0;
UPDATE sys_user SET principal_type = 'NODE'  WHERE role_level >  0;

-- ---------------------------------------------------------------------------
-- 3. 自检
-- ---------------------------------------------------------------------------
SELECT '主体类型分布（应与 role_level 一一对应）' AS check_item,
       principal_type, role_level, COUNT(*) AS cnt
FROM sys_user
GROUP BY principal_type, role_level
ORDER BY principal_type, role_level;

-- 矛盾态：principal_type 与 role_level 判据不一致的行（应为空）
SELECT '矛盾行（应为空）' AS check_item,
       user_id, user_name, principal_type, role_level
FROM sys_user
WHERE (role_level <= 0 AND principal_type <> 'ADMIN')
   OR (role_level >  0 AND principal_type <> 'NODE');

SELECT 'principal_type 列' AS check_item, COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sys_user' AND COLUMN_NAME = 'principal_type';
