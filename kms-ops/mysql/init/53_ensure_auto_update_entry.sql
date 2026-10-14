-- 自动更新入口修复：保证管理端既能配置开关，也能查看并手动触发任务记录。
-- 幂等脚本，适用于已有数据库，不依赖首次初始化时是否执行过 46_auto_update_records_menu.sql。
SET NAMES utf8mb4;

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, route_name,
                      is_frame, is_cache, menu_type, visible, status, perms, icon,
                      create_by, create_time, update_by, update_time, remark)
VALUES (9454, '自动更新任务', 9450, 5, 'autoupdrun', 'autoUpdateRecords/index', '', '',
        1, 0, 'C', '0', '0', '', 'job', 'admin', NOW(), '', NULL,
        '自动更新轮次、手动执行和逐密钥明细')
ON DUPLICATE KEY UPDATE
  menu_name = VALUES(menu_name),
  parent_id = VALUES(parent_id),
  order_num = VALUES(order_num),
  path = VALUES(path),
  component = VALUES(component),
  visible = VALUES(visible),
  status = VALUES(status),
  icon = VALUES(icon),
  remark = VALUES(remark);

INSERT IGNORE INTO sys_role_menu (role_id, menu_id) VALUES (1, 9454);
