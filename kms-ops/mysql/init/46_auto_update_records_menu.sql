-- =============================================================================
-- 46_auto_update_records_menu.sql
-- -----------------------------------------------------------------------------
-- KMS-019：管理端「密钥更新与回收监管」（9450）下新增「自动更新任务」页。
--
-- 这一页回答的问题，改造前**任何地方都答不了**（java-tools-c §1 逐行核实）：
--   本轮跑了没有 / 候选几条 / 成功几条 / 失败几条 / 为什么失败 / 跳过了什么。
-- 改造前 AutoUpdateTask 失败只有一行 log.warn，且失败候选不推进 upd_time ——
-- KYBER/FALCON 这类"服务端造不出新版本"的密钥每 60 秒被重试一次、永不成功。
--
-- 为什么 menu_id 取 9454
-- ----------------------
--   9450 分组现有子项 9451（更新状态）/ 9452（异常密钥）/ 9412（一致性检查）/
--   9413（泄漏关联分析），94xx 段内 9453 已被 9460 的「跨域分发」占用，
--   9454 是 9450 段的空闲号。
--
-- 为什么 path 取 autoupdrun
-- -------------------------
--   path 必须**全局唯一**：后端 `SysMenuServiceImpl.getRouteName()` 用
--   capitalize(path) 当路由名，vue-router 4 在 addRoute 遇到重名时会
--   **先移除旧路由**（36/38/39/41 号脚本都记录过这个坑）。
--   `autoupdrun` 实测未占用（已核对全部 init 脚本中的 path）。
--
-- ⚠️ 三条硬约束（41_*.sql 记录过，务必遵守）
--   【一】子菜单 path 全局唯一（同上）；
--   【二】顶层 menu_type='C' 必须 is_frame=1（照抄同级 9451/9452 的取值）；
--   【三】必须带 SET NAMES utf8mb4（管道导入时客户端字符集不保证，缺了会双重编码）。
--
-- ⚠️ 授权只补 role 1（超级管理员）。这是**管理端监管页**：非管理员虽可调用
--    接口（后端收敛为"只看到影响过自己密钥的轮次"），但监管视角不属于节点端，
--    role 2 不授（照 41_*.sql 把管理页收回 role 2 的口径）。
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
VALUES (9454, '自动更新任务', 9450, 5, 'autoupdrun', 'autoUpdateRecords/index', '', '',
        1, 0, 'C', '0', '0', '', 'job',
        'admin', NOW(), '', NULL,
        'KMS-019：自动更新轮次与逐密钥明细（候选/成功/失败/原因/跳过；管理员可手动补跑一轮）')
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
-- 2. 角色授权（role 1 = 超级管理员；显式补授）
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO sys_role_menu (role_id, menu_id) VALUES (1, 9454);

-- ---------------------------------------------------------------------------
-- 3. 自检：菜单存在 / path 唯一 / role 1 拿得到 / role 2 没拿到
-- ---------------------------------------------------------------------------
SELECT '菜单行' AS chk, COUNT(*) AS n FROM sys_menu WHERE menu_id = 9454 AND menu_name = '自动更新任务';
SELECT 'path 唯一' AS chk, COUNT(*) AS n FROM sys_menu WHERE path = 'autoupdrun';
SELECT 'role 1 已授权' AS chk, COUNT(*) AS n FROM sys_role_menu WHERE role_id = 1 AND menu_id = 9454;
SELECT 'role 2 未授权（期望 0）' AS chk, COUNT(*) AS n FROM sys_role_menu WHERE role_id = 2 AND menu_id = 9454;