-- 修复 sys_menu 中缺失的一级菜单，避免 /getRouters 返回孤儿子菜单
INSERT INTO sys_menu (
  menu_id, menu_name, parent_id, order_num, path, component, `query`, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, update_by, update_time, remark
)
SELECT 4, '系统管理', 0, 4, 'system', NULL, '', '', 1, 0, 'M', '0', '0', '', 'system',
       'admin', NOW(), '', NULL, '系统管理目录'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE menu_id = 4
);

INSERT INTO sys_menu (
  menu_id, menu_name, parent_id, order_num, path, component, `query`, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, update_by, update_time, remark
)
SELECT 5, '系统工具', 0, 5, 'tool', NULL, '', '', 1, 0, 'M', '0', '0', '', 'tool',
       'admin', NOW(), '', NULL, '系统工具目录'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE menu_id = 5
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 2, 4
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 2 AND menu_id = 4
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 2, 5
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 2 AND menu_id = 5
);
