-- =============================================================================
-- 40_fix_node_zone_parent_grants.sql
-- -----------------------------------------------------------------------------
-- 修复 NODE（role_id = 2）动态菜单树缺少三子系统祖先目录的问题。
--
-- 36_three_zone_menus.sql 把既有业务页面重挂到 9400–9430 分区下，但当时
-- 只把这些分区授给管理员。RuoYi 查询普通用户菜单时不会自动补齐未授权祖先，
-- 因此 role 2 虽然仍拥有页面授权，/getRouters 却无法把这些孤儿页面组装进树。
--
-- 本迁移只在 role 2 已经拥有可见、启用的直接业务子页面时，补上对应的目录行。
-- 目录本身 perms 为空，不新增任何接口权限；重复执行由主键与
-- ON DUPLICATE KEY UPDATE 保证幂等。
-- =============================================================================

SET NAMES utf8mb4;

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT child_rm.role_id, zone.menu_id
FROM sys_menu zone
JOIN sys_menu child
  ON child.parent_id = zone.menu_id
JOIN sys_role_menu child_rm
  ON child_rm.role_id = 2
 AND child_rm.menu_id = child.menu_id
WHERE zone.menu_id IN (9400, 9410, 9420, 9430)
  AND zone.menu_type = 'M'
  AND zone.visible = '0'
  AND zone.status = '0'
  AND COALESCE(zone.perms, '') = ''
  AND child.menu_type IN ('M', 'C')
  AND child.visible = '0'
  AND child.status = '0'
ON DUPLICATE KEY UPDATE
  role_id = VALUES(role_id);

-- 自检：role 2 只应看到自己已有业务页面所需的空权限祖先目录。
SELECT zone.menu_id,
       zone.menu_name,
       COALESCE(zone.perms, '') AS perms,
       COUNT(DISTINCT child.menu_id) AS granted_active_children
FROM sys_role_menu zone_rm
JOIN sys_menu zone
  ON zone.menu_id = zone_rm.menu_id
JOIN sys_menu child
  ON child.parent_id = zone.menu_id
JOIN sys_role_menu child_rm
  ON child_rm.role_id = zone_rm.role_id
 AND child_rm.menu_id = child.menu_id
WHERE zone_rm.role_id = 2
  AND zone.menu_id IN (9400, 9410, 9420, 9430)
  AND child.menu_type IN ('M', 'C')
  AND child.visible = '0'
  AND child.status = '0'
GROUP BY zone.menu_id, zone.menu_name, zone.perms
ORDER BY zone.menu_id;
