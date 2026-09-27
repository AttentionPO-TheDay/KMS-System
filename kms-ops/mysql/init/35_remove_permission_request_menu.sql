-- =============================================================================
-- 35_remove_permission_request_menu.sql
-- -----------------------------------------------------------------------------
-- 阶段 8（文档 §8）：下线「权限审批」菜单。
--
-- 为什么删（文档给的新理由，不再用"自己申请自己批"那条）
-- ------------------------------------------------------
-- 节点权限现由 `principal_type`（登录主体）+ 资源属主（canAccess）
-- 直接决定。临时审批流**不承担真实授权作用**：
--   `PermissionRequestService.approve()` 自己注明「刻意**不**调用
--   updateRoleLevel」，即审批通过不授予任何权限；真正的判定是
--   `hasActiveTemporaryPermission(userId)`，而这套判定已随本次一并移除。
-- 继续保留只会形成第二套权限语义 —— 两套并存的系统，出事时没人能说清
-- "这个操作当时到底凭什么被允许"。
--
-- 保留什么
-- --------
-- * `sys_oper_log` 及其页面（操作日志）**保留** —— 那是审计，不是授权。
-- * `permission_request` **表**保留（不删表）：里面是历史审批记录，
--   属于审计材料。只去掉入口，不销毁证据。
--
-- ⚠️ 菜单表本身不能删：侧边栏完全由它驱动。
--
-- 幂等：DELETE + INSERT IGNORE 清理，可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 删除审批菜单（先删子项再删父目录，避免留下悬空 parent）
-- ---------------------------------------------------------------------------
-- 角色映射必须先删：它引用菜单，留着会变成指向不存在菜单的孤儿行，
-- 日后按角色算权限时行为不可预期。
DELETE FROM sys_role_menu WHERE menu_id IN (8002, 8001);
DELETE FROM sys_menu      WHERE menu_id IN (8002, 8001);

-- ---------------------------------------------------------------------------
-- 2. 自检
-- ---------------------------------------------------------------------------
SELECT '残留审批菜单（应为 0）' AS check_item, COUNT(*) AS actual
FROM sys_menu WHERE menu_id IN (8002, 8001)
   OR component LIKE '%permission/request%';

SELECT '残留审批角色映射（应为 0）' AS check_item, COUNT(*) AS actual
FROM sys_role_menu WHERE menu_id IN (8002, 8001);

-- 操作日志必须还在（审计保留）
SELECT '操作日志菜单（应 > 0）' AS check_item, COUNT(*) AS actual
FROM sys_menu WHERE component LIKE '%operlog%' OR path = 'operlog';

-- permission_request 表必须还在（历史证据保留）
SELECT 'permission_request 表仍在' AS check_item, COUNT(*) AS tables_found
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'permission_request';
