-- =============================================================================
-- 44_add_node_self_authorization_menu.sql
-- -----------------------------------------------------------------------------
-- 任务书「节点多级授权」：在**节点端**「密钥分发」组下新增「节点授权」页。
--
-- 这一页是整条链路的入口：节点看到全网名录 → 申请与某节点建立会话 →
-- 管理员在**管理端**「节点分发授权」页（菜单 9006）审批 → 双向放行。
-- 因此本脚本只加**节点端**这一条菜单；管理端不新增页面（审批区直接嵌在 9006 页里）。
--
-- 为什么 id 取 9476 / path 取 selfauth
-- ------------------------------------
--   * 9476 是 94xx 段（节点端）当前的空闲号（9400~9475 已占用）；
--   * path 必须**全局唯一**：后端 `SysMenuServiceImpl.getRouteName()` 用
--     capitalize(path) 当路由名，而 vue-router 4 在 addRoute 遇到重名时会
--     **先移除旧路由**（36/38/39/41 号脚本都记录过这个坑）。
--     `selfauth` 已实测未占用（distribute 用 keydist、会话管理用 selfsess、
--     密钥池用 selfpool、当前节点用 selfnode）。
--
-- ⚠️ 三条硬约束（41_*.sql 记录过，务必遵守）
--   【一】子菜单 path 全局唯一（同上）；
--   【二】顶层 menu_type='C' 必须 is_frame=1（子菜单照抄同级 9471~9475 的取值）；
--   【三】必须带 SET NAMES utf8mb4（管道导入时客户端字符集不保证，缺了会双重编码）。
--
-- ⚠️ 角色授权是**显式列表**（41_*.sql:305-325）：只补 role 2（节点端）。
--    管理员不拿这一页 —— 他们用的是管理端 9006。
--
-- 幂等：INSERT … ON DUPLICATE KEY UPDATE + INSERT IGNORE，可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 菜单行
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, route_name,
                      is_frame, is_cache, menu_type, visible, status, perms, icon,
                      create_by, create_time, update_by, update_time, remark)
VALUES (9476, '节点授权', 9420, 6, 'selfauth', 'selfAuth/index', '', '',
        1, 0, 'C', '0', '0', '', 'peoples',
        'admin', NOW(), '', NULL,
        '节点发起对端授权申请、查看我的申请；审批在管理端「节点分发授权」页')
ON DUPLICATE KEY UPDATE
    menu_name = VALUES(menu_name),
    parent_id = VALUES(parent_id),
    order_num = VALUES(order_num),
    path      = VALUES(path),
    component = VALUES(component),
    is_frame  = VALUES(is_frame),
    menu_type = VALUES(menu_type),
    visible   = VALUES(visible),
    status    = VALUES(status),
    icon      = VALUES(icon),
    remark    = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 2. 角色授权（role 2 = 节点端；显式补授，不依赖"补祖先"那套）
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO sys_role_menu (role_id, menu_id) VALUES (2, 9476);

-- ---------------------------------------------------------------------------
-- 3. 自检：菜单存在 / path 唯一 / role 2 拿得到
-- ---------------------------------------------------------------------------
SELECT '菜单行' AS chk, COUNT(*) AS n FROM sys_menu WHERE menu_id = 9476 AND menu_name = '节点授权';
SELECT 'path 唯一' AS chk, COUNT(*) AS n FROM sys_menu WHERE path = 'selfauth';
SELECT 'role 2 已授权' AS chk, COUNT(*) AS n FROM sys_role_menu WHERE role_id = 2 AND menu_id = 9476;
