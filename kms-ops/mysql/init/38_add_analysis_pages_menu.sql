-- =============================================================================
-- 38_add_analysis_pages_menu.sql
-- -----------------------------------------------------------------------------
-- 阶段 9 补齐：把 §9.3 列的三个页面接入菜单。
--
-- 为什么上一版（36_*.sql）没挂它们
-- ------------------------------
-- 当时**页面不存在**。挂空菜单会点出 404，比没有菜单更糟 ——
-- 用户会以为页面坏了，而不是"这个功能还没做"。
-- 现在三个页面的前端已就位，才补上菜单。
--
-- 对应的后端接口（阶段 4 / 阶段 7 已实现）：
--   版本历史        GET /lifecycle/keymanage/{keyId}/versions
--   一致性与异常分析 GET /lifecycle/keymanage/health/{keyId}
--   泄漏关联分析     GET /lifecycle/keymanage/analysis/{keyId}
--
-- 归属：文档 §9.3 把「版本历史」「一致性检查」「异常/泄漏分析」列在
-- **密钥更新与回收**分区下（它们考察的是密钥在生命周期中的状态演进）。
--
-- ⚠️ child path 必须全局唯一：后端 getRouteName() = capitalize(path)，
--    vue-router 4 遇重名会**先移除旧路由**（见 30_*.sql 的详细说明）。
--    已占用集合里没有 version/health/leak，故直接使用。
--
-- 幂等：INSERT ... ON DUPLICATE KEY UPDATE。
-- =============================================================================

SET NAMES utf8mb4;

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9411, '版本历史', 9410, 4, 'version', 'keyVersionHistory/index', 1, 0,
  'C', '0', '0', '', 'time-range', 'admin', NOW(),
  '阶段9：展示轮换/回收归档的历史版本快照（读取 /{keyId}/versions）'),
 (9412, '一致性与异常分析', 9410, 5, 'health', 'keyHealth/index', 1, 0,
  'C', '0', '0', '', 'shield', 'admin', NOW(),
  '阶段9：密钥一致性检查 + 规则化异常检测（读取 /health/{keyId}）'),
 (9413, '泄漏关联分析', 9410, 6, 'leak', 'keyLeakAnalysis/index', 1, 0,
  'C', '0', '0', '', 'search', 'admin', NOW(),
  '阶段9：查出该密钥影响到的分发与操作范围（读取 /analysis/{keyId}）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon),
                        remark = VALUES(remark);

INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9411), (1, 9412), (1, 9413)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- ---------------------------------------------------------------------------
-- 自检
-- ---------------------------------------------------------------------------
SELECT '新增分析类菜单' AS check_item, menu_id, menu_name, parent_id, path, component, order_num
FROM sys_menu WHERE menu_id IN (9411, 9412, 9413) ORDER BY menu_id;

-- 路由名唯一性（应只有一条，即刚插入的 'version'）
SELECT 'path=version 的行数（应为 1）' AS check_item, COUNT(*) AS cnt
FROM sys_menu WHERE LOWER(path) = 'version';

-- 全局重名扫描：menu_type 为 M/C 的才是路由来源，F 是按钮不参与
SELECT '路由名冲突（应为空）' AS check_item, LOWER(path) AS colliding_path, COUNT(*) AS cnt
FROM sys_menu
WHERE status = '0' AND menu_type IN ('M', 'C')
GROUP BY LOWER(path) HAVING COUNT(*) > 1;