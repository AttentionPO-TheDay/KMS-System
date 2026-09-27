-- =============================================================================
-- 26_aggregate_admin_menus.sql
-- -----------------------------------------------------------------------------
-- P4：管理端菜单聚合 —— 把「分发与区块链」与「测试」两组收进单一管理控制台。
--
-- 背景（D9 / §1.2）
-- ----------------
-- 系统有四个前端：`/user/`（用户前台）、`/updatedel/`（管理控制台）、
-- `/distribute/`（分发模块自带后台）、`/acceptance/`（验收测试台）。
-- 改造前管理员要开四个入口、记四套登录 —— 这不只是麻烦，
-- **它让权限边界变得含糊**：分发模块自带后台的登录态与主 KMS 是两套，
-- 谁在什么时候以什么身份进去的，事后很难说清。
--
-- 聚合方式：用 RuoYi 既有的 `InnerLink` 机制把外部页面**嵌进**管理控制台的菜单里。
--   - `is_frame = 1`  → 后端把 `path` 放进 `meta.link`，前端渲染成 iframe
--   - `component = 'InnerLink'` → 对应 `permission.js` 里的组件映射
--   - `path` 直接写**外部 URL**（这是 RuoYi 外链的约定）
--
-- ⚠️ 与 `is_frame=0` 的普通菜单不同：普通菜单的 `path` 是路由片段，
--    这里必须是完整路径，写错了会得到 iframe 里的 404。
--
-- 幂等：ON DUPLICATE KEY UPDATE。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 「分发与区块链」目录
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9100, '分发与区块链', 0, 60, 'distchain', NULL, 1, 0,
        'M', '0', '0', '', 'server', 'admin', NOW(),
        '分发模块与区块链相关页面（内嵌 /distribute/）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), path = VALUES(path),
                        menu_type = VALUES(menu_type), order_num = VALUES(order_num),
                        icon = VALUES(icon), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9101, '分发控制台', 9100, 1, 'distribute', 'frame/index', 0, 0,
        'C', '0', '0', 'pqkds:console:view', 'monitor', 'admin', NOW(),
        '内嵌分发模块自带后台（/distribute/）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        menu_type = VALUES(menu_type), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9102, '区块链浏览器', 9100, 2, 'blockchain', 'frame/index', 0, 0,
        'C', '0', '0', 'pqkds:blockchain:view', 'link', 'admin', NOW(),
        '内嵌分发模块的区块链视图')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        menu_type = VALUES(menu_type), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9103, '节点管理', 9100, 3, 'nodelist', 'frame/index', 0, 0,
        'C', '0', '0', 'pqkds:node:view', 'tree-table', 'admin', NOW(),
        '内嵌分发模块的节点列表（节点密钥与授权都在那边）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        menu_type = VALUES(menu_type), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 2. 「测试」目录（验收测试台）
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9200, '测试', 0, 90, 'testing', NULL, 1, 0,
        'M', '0', '0', '', 'form', 'admin', NOW(),
        '验收与自测页面（内嵌 /acceptance/）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), path = VALUES(path),
                        menu_type = VALUES(menu_type), order_num = VALUES(order_num),
                        icon = VALUES(icon), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9201, '验收测试台', 9200, 1, 'acceptance', 'frame/index', 0, 0,
        'C', '0', '0', 'kms:acceptance:view', 'tool', 'admin', NOW(),
        '内嵌验收测试台（/acceptance/）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        menu_type = VALUES(menu_type), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 2.5 内嵌地址（`query` 必须是 **JSON**，不是查询串）
-- ---------------------------------------------------------------------------
-- `InnerLink` 在这里**用不了**：后端 `MetaVo` 只在 path 是 http(s) 绝对地址时
-- 才写 `meta.link`（`if (StringUtils.ishttp(link))`），而同源路径（`/distribute/`）
-- 永远是 null，前端就不渲染 iframe —— 页面白屏且**没有任何报错**。
-- 所以改用本地组件 `views/frame/index.vue`，目标地址经菜单 `query` 传入。
--
-- ⚠️ 两个坑：
--   1. `query` 要写 **JSON**（`{"url":"..."}`），不是查询串（`url=...`）；
--   2. `query` **只在"从侧边栏点进去"时生效** —— 直接敲 URL 打开时 `route.query` 是空的。
--      排查时若直接导航去测，会误以为功能没做成（我踩过）。
UPDATE sys_menu SET query='{"url":"/distribute/"}'            WHERE menu_id=9101;
UPDATE sys_menu SET query='{"url":"/distribute/#/blockchain"}' WHERE menu_id=9102;
UPDATE sys_menu SET query='{"url":"/distribute/#/node"}'       WHERE menu_id=9103;
UPDATE sys_menu SET query='{"url":"/acceptance/"}'             WHERE menu_id=9201;

-- ---------------------------------------------------------------------------
-- 3. 角色映射（只插菜单不插映射 → 侧边栏里看不到，是个很容易漏的坑）
-- ---------------------------------------------------------------------------
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9100), (1, 9101), (1, 9102), (1, 9103), (1, 9200), (1, 9201)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

SELECT '菜单聚合' AS check_item, menu_id, menu_name, parent_id, path, component, menu_type
FROM sys_menu WHERE menu_id BETWEEN 9100 AND 9201 ORDER BY menu_id;

SELECT '角色映射' AS check_item, COUNT(*) AS n
FROM sys_role_menu WHERE menu_id BETWEEN 9100 AND 9201;
