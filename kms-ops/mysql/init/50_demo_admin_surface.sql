-- Demo 管理端收敛：节点管理/节点授权/验收测试台 + 密钥全生命周期。
-- 节点端 role=2 不受影响；系统用户、角色等基础管理菜单也不受影响。
SET NAMES utf8mb4;

-- 41 号迁移曾把生成、更新回收、分发监管等详情页全部授予管理员。
-- Demo 管理端只保留汇总入口，避免管理员误入节点侧明细和真实业务操作页。
DELETE FROM sys_role_menu
WHERE role_id = 1
  AND menu_id IN (
    9260, 9440, 9441, 9442, 9021,
    9450, 9451, 9452, 9412, 9413,
    9460, 9101, 9104, 9105, 9453,
    9102, 9280, 9461
  );

-- 允许的 Demo 管理入口：验收、节点管理/授权、密钥总览。
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9201), (1, 9470), (1, 9103), (1, 9005), (1, 9006), (1, 9431)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- 只读总览菜单名称、位置和说明保持幂等。
UPDATE sys_menu
SET menu_name = '密钥全生命周期', parent_id = 0, order_num = 0,
    path = 'secmonitor', component = 'securityMonitor/index',
    menu_type = 'C', visible = '0', status = '0', is_frame = 1,
    remark = 'Demo 管理端只读汇总：密钥、节点、池项、会话与分发结果，不含密钥详情或节点操作'
WHERE menu_id = 9431;

SELECT 'Demo 管理入口' AS check_item, menu_id, menu_name, parent_id, path
FROM sys_menu
WHERE menu_id IN (9201, 9470, 9103, 9005, 9006, 9431);
