-- Demo 管理端只读数据按模块分栏：不再把所有内容堆在“密钥全生命周期”一页。
SET NAMES utf8mb4;

DELETE FROM sys_role_menu WHERE role_id = 1 AND menu_id = 9431;

INSERT INTO sys_menu
  (menu_id, menu_name, parent_id, order_num, path, component, query, route_name,
   is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, remark)
VALUES
  (9480, '密钥数据', 0, 0, 'admindata', NULL, '', 'AdminData', 1, 0, 'M', '0', '0', '', 'key', 'admin', '管理员只读数据分区'),
  (9481, '密钥总览', 9480, 1, 'keys', 'adminSummary/keys', '', 'AdminKeySummary', 1, 0, 'C', '0', '0', '', 'key', 'admin', '逻辑密钥与异常计数，只读'),
  (9482, '预分配池', 9480, 2, 'pool', 'adminSummary/pool', '', 'AdminPoolSummary', 1, 0, 'C', '0', '0', '', 'database', 'admin', '预分配保护包状态，只读'),
  (9483, '会话数据', 9480, 3, 'sessions', 'adminSummary/sessions', '', 'AdminSessionSummary', 1, 0, 'C', '0', '0', '', 'message', 'admin', '节点会话状态，只读'),
  (9484, '分发批次', 9480, 4, 'distributions', 'adminSummary/distributions', '', 'AdminDistributionSummary', 1, 0, 'C', '0', '0', '', 'share', 'admin', '分发批次与跨域结果，只读')
ON DUPLICATE KEY UPDATE
  menu_name = VALUES(menu_name), parent_id = VALUES(parent_id), order_num = VALUES(order_num),
  path = VALUES(path), component = VALUES(component), menu_type = VALUES(menu_type),
  visible = VALUES(visible), status = VALUES(status), remark = VALUES(remark);

INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9480), (1, 9481), (1, 9482), (1, 9483), (1, 9484)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);
