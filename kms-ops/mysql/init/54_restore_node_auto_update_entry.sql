-- 恢复节点端“密钥更新 -> 自动更新设置”入口。
-- 6000 曾在 41_admin_node_menu_split.sql 中被隐藏，导致页面和配置按钮
-- 虽然仍在代码与后端，却无法从节点侧进入。该脚本可安全重复执行。
SET NAMES utf8mb4;

UPDATE sys_menu
SET parent_id = 9410,
    order_num = 3,
    menu_name = '自动更新',
    path = 'keyautoupdate',
    component = 'keyautoupdate/index',
    visible = '0',
    status = '0',
    menu_type = 'C',
    perms = 'keymanage:keymanage:edit',
    remark = '节点侧配置用户密钥自动更新，并查看最近执行结果'
WHERE menu_id = 6000;

INSERT IGNORE INTO sys_role_menu (role_id, menu_id) VALUES (2, 6000);

-- 2004 是 6000 的“配置自动更新”按钮权限。历史迁移清理过它，需随入口恢复。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id) VALUES (2, 2004);

SELECT '节点自动更新入口' AS check_item, menu_id, menu_name, parent_id, path, visible, status
FROM sys_menu
WHERE menu_id = 6000;
SELECT '节点自动更新授权' AS check_item, role_id, menu_id
FROM sys_role_menu
WHERE role_id = 2 AND menu_id IN (6000, 2004)
ORDER BY menu_id;
