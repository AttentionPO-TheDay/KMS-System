-- =============================================================================
-- 43_remove_duplicate_overview_menu.sql
-- -----------------------------------------------------------------------------
-- 去掉管理端**重复的**总览入口（2026-09-30 用户反馈）。
--
-- 问题
-- ----
-- 管理端侧边栏里同时有两条指向**同一个页面**的菜单：
--
--   总览仪表盘   path=/index    component=views/index.vue   ← 静态路由（router/index.js，affix）
--   系统总览     path=console   component=views/index.vue   ← 本仓库 41_*.sql 新增的菜单
--
-- 两者 component 相同，点进去是同一个页面 —— 只是入口重复。
--
-- 为什么保留「总览仪表盘」、删掉「系统总览」
-- ----------------------------------------
-- `/index` 是**框架既有的管理员首页**，多处接线依赖它：
--   * 根路径 `/` 的 redirect 指向它（router/index.js）
--   * 面包屑「首页」的跳转目标（components/Breadcrumb/index.js）
--   * 侧边栏 Logo 的链接、404 页的「返回首页」、顶栏退出登录的回跳
-- 删它要动这一整片框架接线，收益只是"少一条菜单"。
-- 而 9260 是 41_*.sql 新增的重复项，藏掉它即可 —— 改动面最小、风险最低。
--
-- 为什么只隐藏不删除
-- ------------------
-- 与 41_*.sql 的处理一致：`sys_menu` 是侧边栏的唯一来源，删行会连带影响
-- 授权与历史引用。设 `visible='1'` 后它不再下发，将来要恢复也只是改回 '0'。
--
-- ⚠️ 若日后希望管理端口径与文档 §11.1 一致（首项叫「系统总览」而不是
--    「总览仪表盘」），正确做法是**改静态路由的 title**（router/index.js 里
--    `/index` 的 meta.title），而不是把这条菜单重新打开 —— 否则重复会再来一次。
--
-- 幂等：UPDATE / DELETE，可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

-- 1) 隐藏重复的总览菜单
UPDATE sys_menu SET visible = '1' WHERE menu_id = 9260;

-- 2) 撤掉它的角色授权（留着授权不会让它重新出现，但会让"role 1 到底能看什么"
--    对不上账 —— 本仓库的授权是显式列表，藏了菜单就该同时撤授权）
DELETE FROM sys_role_menu WHERE menu_id = 9260;

-- ---------------------------------------------------------------------------
-- 自检
-- ---------------------------------------------------------------------------
SELECT '重复总览菜单应已隐藏' AS check_item, menu_id, menu_name, path, visible
FROM sys_menu WHERE menu_id = 9260;

SELECT '指向 views/index.vue 的**可见**菜单（应为空）' AS check_item,
       menu_id, menu_name, path, component
FROM sys_menu
WHERE component = 'index' AND visible = '0';

-- 管理端顶层（role 1）现在应该有且只有一个总览入口
SELECT '管理端顶层条目' AS check_item, c.menu_id, c.menu_name, c.path, c.order_num
FROM sys_role_menu rm
JOIN sys_menu c ON c.menu_id = rm.menu_id
WHERE rm.role_id = 1 AND c.parent_id = 0 AND c.visible = '0' AND c.menu_type IN ('M', 'C')
ORDER BY c.order_num;
