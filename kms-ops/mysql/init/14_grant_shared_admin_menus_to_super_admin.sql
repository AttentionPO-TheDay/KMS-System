-- 给超级管理员补齐统一后台菜单授权，否则 /getRouters 不会返回这些菜单
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 4
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 4
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 100
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 100
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 101
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 101
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 102
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 102
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 108
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 108
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 500
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 500
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, 501
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu WHERE role_id = 1 AND menu_id = 501
);
