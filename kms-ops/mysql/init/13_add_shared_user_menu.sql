SET NAMES utf8mb4;
-- 为三大系统补齐统一后台中的用户管理菜单
INSERT INTO sys_menu (
  menu_id, menu_name, parent_id, order_num, path, component, `query`, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, update_by, update_time, remark
)
SELECT 100, '用户管理', 4, 0, 'user', 'system/user/index', '', '', 1, 0, 'C', '0', '0', 'system:user:list', 'user',
       'admin', NOW(), '', NULL, '用户管理菜单'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE menu_id = 100
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 2, 100
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 2 AND menu_id = 100
);
