-- 恢复管理员逻辑域管理，不授予节点端任何全局管理操作。
SET NAMES utf8mb4;
INSERT INTO sys_menu
  (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
   menu_type, visible, status, perms, icon, create_by, remark)
VALUES (9461, '域管理', 9470, 3, 'domains', 'domains/index', 1, 0,
        'C', '0', '0', '', 'international', 'admin', '逻辑域分布及节点域归属管理；历史分发域快照不变')
ON DUPLICATE KEY UPDATE menu_name=VALUES(menu_name), parent_id=VALUES(parent_id),
  order_num=VALUES(order_num), path=VALUES(path), component=VALUES(component),
  visible=VALUES(visible), status=VALUES(status), icon=VALUES(icon), remark=VALUES(remark);
INSERT INTO sys_role_menu (role_id, menu_id) VALUES (1, 9470), (1, 9461)
ON DUPLICATE KEY UPDATE role_id=VALUES(role_id);
UPDATE sys_menu SET icon='database' WHERE menu_id=9482;
