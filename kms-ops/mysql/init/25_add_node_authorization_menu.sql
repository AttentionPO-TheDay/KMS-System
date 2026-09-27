-- =============================================================================
-- 25_add_node_authorization_menu.sql
-- -----------------------------------------------------------------------------
-- 给管理控制台加「节点鉴权」菜单（P3 步骤 10 / D5）。
--
-- 这个页面管的是"普通用户能向哪些节点分发密钥"。没有它，管理员只能手工改库 ——
-- 而授权是安全边界，不该靠手工 SQL 维护。
--
-- 与前端路由的关系
-- ----------------
-- 页面同时有**静态路由**（`kms-updatedel/front/src/router/index.js` 的 `/nodeauth/index`）
-- 与这里的菜单行。静态路由保证"即使菜单没插好，页面依然可达"，
-- 菜单行只负责让它出现在侧边栏。两者不是二选一 —— 把可达性绑在菜单数据上，
-- 会让一次菜单事故变成功能整体不可用。
--
-- 幂等：ON DUPLICATE KEY UPDATE。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 菜单结构：必须是「目录(M) + 菜单(C)」两级
-- ---------------------------------------------------------------------------
-- 一开始只插了一条 `menu_type='C'`、`parent_id=0` 的记录，结果**侧边栏里没有它**：
-- RuoYi 的 `getRouters` 是按"顶层目录 → 挂子菜单"组织的，
-- 顶层直接放一个 `C` 不会出现在菜单树里（页面能通过 URL 打开，接口也正常，
-- 所以现象很像"菜单没生效"，其实是结构不对）。
-- 这里照 9001（目录 key）+ 5000（页面 keyupdate）的形状来。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9005, '节点鉴权', 0, 55, 'nodeauth', NULL, 1, 0,
        'M', '0', '0', '', 'tree', 'admin', NOW(),
        '用户可通信节点授权（目录）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        order_num = VALUES(order_num), icon = VALUES(icon), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9006, '节点鉴权', 9005, 1, 'index', 'nodeauth/index', 1, 0,
        'C', '0', '0', 'nodeauth:authorization:list', 'tree', 'admin', NOW(),
        '授权/撤销普通用户可通信的节点（单子目录会被折叠显示，故子项名与目录同名）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        menu_type = VALUES(menu_type), remark = VALUES(remark);

SELECT '节点鉴权菜单' AS check_item, menu_id, menu_name, parent_id, path, component, menu_type
FROM sys_menu WHERE menu_id IN (9005, 9006) ORDER BY menu_id;

-- ---------------------------------------------------------------------------
-- 角色映射：菜单必须挂到角色上才会出现在侧边栏
-- ---------------------------------------------------------------------------
-- 只插菜单不插映射是个很容易漏的坑：页面能通过 URL 打开、接口也都正常，
-- 但侧边栏里就是没有它 —— 现象像"菜单没生效"，实际是权限关联缺失。
-- 与 9001–9004 保持一致，挂到 role_id=1（管理员）。
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9005), (1, 9006)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

SELECT '角色映射' AS check_item, rm.role_id, r.role_name, rm.menu_id
FROM sys_role_menu rm JOIN sys_role r ON r.role_id = rm.role_id
WHERE rm.menu_id IN (9005, 9006) ORDER BY rm.menu_id;
