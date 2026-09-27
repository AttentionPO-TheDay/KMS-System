-- =============================================================================
-- 32_trim_common_role_grants.sql
-- -----------------------------------------------------------------------------
-- 阶段 2：把「普通角色」(role_id=2) 的授权收敛到**业务范围**，并补上节点入口。
--
-- 为什么必须做这一步（不是可选的清理）
-- ----------------------------------
-- RuoYi 的 `02.sql` 基线给 role_id=2 授了整套**系统管理**与**监控日志**菜单，
-- 包括 `system:user:list` / `system:role:add|edit|remove` / `monitor:operlog:remove`
-- 等管理权限。而本系统里 role_id=2 的实际持有点是：
--   * 新创建的**区块链节点**账号（node_account_service 挂的就是 role 2）
--   * 旧测试账号 yx / acceptance_user
-- 也就是说「普通用户」这个角色，实际就是节点的角色。
--
-- 2026-09-27 实测（用 yx 的令牌直连后端）：
--     GET /updatedel-api/system/role/list     → 200，返回角色数据
--     GET /updatedel-api/system/user/list     → 200，返回用户数据
--     GET /updatedel-api/monitor/operlog/list → 200，返回操作日志
-- **后端按权限串放行、并不做管理员校验**，所以这些授权就是真实可达的能力，
-- 不是"菜单看不见而已"。
--
-- 为什么现在必须修：阶段 2 的路由守卫放行了 NODE 主体（此前节点被
-- `isAdminLevel` 挡在 /401 之外，一个业务页都进不去）。放行之后，
-- 节点会拿到 `getRouters()` 按 role 2 下发的菜单 —— 若不同时收掉这些
-- 管理权限，等于**把系统管理界面对所有节点敞开**，比阶段 1 的问题更严重。
--
-- 收敛原则
-- --------
--   收掉：system:*（用户/角色管理及其按钮）、monitor:*（操作/登录日志及其按钮）
--   补上：阶段 1 迁入的业务页（工作台/我的日志/密钥分发/对称密钥/生成密钥）
--
-- ⚠️ 保留的部分没有动：`keymanage:*` 与密钥查询/算法说明等业务菜单仍在，
--    节点需要它们做密钥业务。
--
-- ⚠️ 依赖：9050–9054 由 `30_port_user_pages_into_console.sql` 建立，
--    因此本脚本必须排在 30 之后执行。
--
-- 幂等：全部为 DELETE / INSERT ... ON DUPLICATE KEY UPDATE，可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 记录收敛前的情况（执行日志里留痕，便于回溯与对比）
-- ---------------------------------------------------------------------------
SELECT '收敛前 role=2 的授权数' AS check_item, COUNT(*) AS grants_before
FROM sys_role_menu WHERE role_id = 2;

-- ---------------------------------------------------------------------------
-- 2. 收掉系统管理与监控日志的授权
-- ---------------------------------------------------------------------------
-- 用菜单本身的条件来删，而不是硬编码一堆 menu_id：这样即使上游迁移调整过
-- 菜单编号，只要权限串语义没变，本脚本依然收敛得对。
DELETE rm FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE rm.role_id = 2
  AND (m.perms LIKE 'system:%' OR m.perms LIKE 'monitor:%');

-- 目录节点（perms 为空）单独删：它们是「系统管理」(4) 与「日志审计」(108)，
-- 在子项被摘掉后只会留下两个空分组，反而让人以为页面坏了。
DELETE FROM sys_role_menu WHERE role_id = 2 AND menu_id IN (4, 108);

-- ---------------------------------------------------------------------------
-- 3. 补上节点业务入口
-- ---------------------------------------------------------------------------
-- 9050–9054 是阶段 1 从 kms-user 迁入的业务页，当时只授给了管理员(role 1)。
-- 节点是这些页面的真正使用者，必须补授权，否则节点登录后侧边栏是空的。
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (2, 9050), (2, 9051), (2, 9052), (2, 9053), (2, 9054)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- ---------------------------------------------------------------------------
-- 4. 自检
-- ---------------------------------------------------------------------------
SELECT '收敛后 role=2 的授权数' AS check_item, COUNT(*) AS grants_after
FROM sys_role_menu WHERE role_id = 2;

-- 关键断言：role 2 **不得**残留任何管理类权限串。期望为空集。
-- 有行返回就说明还有管理能力漏给了节点，必须补齐删除条件后再上线。
SELECT 'role=2 残留管理权限（应为空）' AS check_item, m.menu_id, m.perms
FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE rm.role_id = 2
  AND (m.perms LIKE 'system:%' OR m.perms LIKE 'monitor:%');

-- 节点应当拿到的五个业务菜单
SELECT 'role=2 业务菜单' AS check_item, m.menu_id, m.menu_name, m.path
FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE rm.role_id = 2 AND m.menu_id BETWEEN 9050 AND 9054
ORDER BY m.menu_id;

-- 对照：管理员(role 1)的授权不应受影响
SELECT 'role=1 授权数（不应变化）' AS check_item, COUNT(*) AS admin_grants
FROM sys_role_menu WHERE role_id = 1;
