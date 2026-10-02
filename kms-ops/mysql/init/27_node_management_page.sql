-- =============================================================================
-- 27_node_management_page.sql
-- -----------------------------------------------------------------------------
-- 把「节点管理」（menu_id=9103）从 **iframe 内嵌分发模块** 改成 **管理端原生页面**。
--
-- 为什么要改（2026-09-24 实测，有截图）
-- -------------------------------------
-- 原配置是 `component='frame/index'` + `query='{"url":"/distribute/#/node"}'`，
-- 即用 iframe 嵌 django-vue3-admin 的 `/#/node`。接口层看不出任何问题：
--   * 菜单查得到、iframe 的 src 正确、`/pqkds-api/nodes/` 返回 200 且有 2 个节点；
--   * 但 iframe 里渲染出来的是**那个子应用自己的登录页** ——
--     "抗量子分发系统 欢迎您！/ 账号密码登录 / 登 录"。
--   管理员已经登录管理端，点进来却要求再登一次，而且那个登录态与主 KMS 是两套。
--   用 curl 验证永远发现不了这一点，它只在渲染后出现（tools/verify-node-page.mjs 抓的就是它）。
--
-- 改法：新增原生页 `views/nodes/index.vue` + `api/nodes/nodes.js`，
-- 直接调 `/pqkds-api/nodes/*`，复用管理端登录态，不再有第二次登录。
--
-- 边界（写清楚免得日后误解）：这一页管的是**分发系统的业务节点**
-- （`falcon_kds.dvadmin_pqkds_nodes` 表：谁可以向谁分发密钥），**不是 FISCO 链的记账节点**。
-- 因此它与链是否出块无关 —— 链挂了这一页照样能用。
--
-- 幂等：ON DUPLICATE KEY UPDATE。
-- =============================================================================

-- 1. 菜单指向原生组件；`query` 必须清空，否则 frame 组件残留的目标地址会误导排查
-- ⚠️ 必须有这一行（2026-09-30 补）：本文件含中文，而**管道导入**
--    （docker-entrypoint-initdb.d / docker exec -i ... mysql < file）时
--    客户端字符集不保证是 utf8mb4。缺了它中文会按单字节解析后再以 utf8mb4 存储，
--    即**双重编码** —— 库里存的是 C3A5C2B7... 这类字节，前端渲染成「å·¥ä½œå°」。
--    本文件此前正因缺这一行，把 20 个菜单名写坏（由 42_*.sql 修复）。
SET NAMES utf8mb4;

UPDATE sys_menu
SET component = 'nodes/index',
    path      = 'nodes',
    query     = '',
    is_frame  = 0,
    remark    = '分发系统演示节点（原生页面，数据来自 dvadmin_pqkds_nodes 表，不依赖链）'
WHERE menu_id = 9103;

-- 2. 权限标识沿用原值（列表权限），新增/编辑/删除复用同一标识：
--    分发模块的 NodeViewSet 对这些动作本就不校验身份，前端再细分标识只是摆设。
UPDATE sys_menu
SET perms = 'pqkds:node:view'
WHERE menu_id = 9103;

-- 3. 角色映射兜底（原有映射可能因重装而缺失）
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9103)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

SELECT '节点管理菜单' AS check_item, menu_id, menu_name, parent_id, path, component, query
FROM sys_menu WHERE menu_id = 9103;
