-- 独立域登记及管理员跨域记录入口，节点业务授权保持不变。
SET NAMES utf8mb4;
INSERT INTO sys_menu
  (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
   menu_type, visible, status, perms, icon, create_by, remark)
VALUES (9453, '跨域分发记录', 9480, 6, 'crossdom', 'crossDomain/index', 1, 0,
        'C', '0', '0', '', 'international', 'admin', '按分发时的域快照监管，不提供管理员代节点分发')
ON DUPLICATE KEY UPDATE menu_name=VALUES(menu_name), parent_id=VALUES(parent_id),
  order_num=VALUES(order_num), path=VALUES(path), component=VALUES(component),
  visible=VALUES(visible), status=VALUES(status), icon=VALUES(icon), remark=VALUES(remark);
INSERT INTO sys_role_menu (role_id, menu_id) VALUES (1, 9453)
ON DUPLICATE KEY UPDATE role_id=VALUES(role_id);
UPDATE sys_menu SET remark='独立新增逻辑域及调整节点域归属，保留空域' WHERE menu_id=9461;
