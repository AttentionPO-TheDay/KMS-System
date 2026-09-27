-- =============================================================================
-- 39_add_security_monitor_menu.sql
-- -----------------------------------------------------------------------------
-- 阶段 7 §8.7：安全监控总览菜单。
--
-- 数据源：GET /pqkds-api/pqkds/security-monitor/summary/
-- （`security_monitor_views.py`，管理员视角聚合统计，需登录态）
--
-- 归属「综合管理」——它是治理视角的全局面板，不属于三个业务子系统。
--
-- ⚠️ child path 全局唯一：后端 getRouteName() = capitalize(path)，
--    vue-router 4 遇重名先移除旧路由。`monitor` 未被占用，但用
--    `secmonitor` 更不易与将来可能的其它监控页冲突。
--
-- 幂等：INSERT ... ON DUPLICATE KEY UPDATE。
-- =============================================================================

SET NAMES utf8mb4;

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9431, '安全监控', 9430, 10, 'secmonitor', 'securityMonitor/index', 1, 0,
        'C', '0', '0', '', 'monitor', 'admin', NOW(),
        '阶段7 §8.7：活跃节点/密钥/预分配池/会话/异常/分发成功率总览')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon),
                        remark = VALUES(remark);

INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9431)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- ---------------------------------------------------------------------------
-- 自检
-- ---------------------------------------------------------------------------
SELECT '安全监控菜单' AS check_item, menu_id, menu_name, parent_id, path, component, order_num
FROM sys_menu WHERE menu_id = 9431;

SELECT '路由名冲突（应为空）' AS check_item, LOWER(path) AS colliding_path, COUNT(*) AS cnt
FROM sys_menu WHERE status = '0' AND menu_type IN ('M', 'C')
GROUP BY LOWER(path) HAVING COUNT(*) > 1;