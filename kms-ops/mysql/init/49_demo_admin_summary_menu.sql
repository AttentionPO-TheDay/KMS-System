-- Demo admin summary is one of four functional entrances. Preserve migration 48.
SET NAMES utf8mb4;
UPDATE sys_menu
SET menu_name = '密钥总览', parent_id = 0, order_num = 0,
    path = 'secmonitor', component = 'securityMonitor/index',
    menu_type = 'C', visible = '0', status = '0', is_frame = 1, is_cache = 0,
    remark = '管理员只读聚合：逻辑密钥、节点、池项、会话与分发批次；不含密钥详情'
WHERE menu_id = 9431;
INSERT INTO sys_role_menu (role_id, menu_id) VALUES (1, 9431)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);
