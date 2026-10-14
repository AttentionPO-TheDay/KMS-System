-- =============================================================================
-- 48_rehome_node_analysis_and_symmetric_keys.sql
-- -----------------------------------------------------------------------------
-- 节点端功能归位：
--   1) 节点可以查看发给自己的对称密钥信封；
--   2) 一致性/异常/泄漏分析属于密钥生成后的材料检查，挂在「密钥生成」下，
--      不再作为管理端生命周期监管入口；
--   3) 管理端继续保留汇总、审批与验收测试台。
-- =============================================================================

SET NAMES utf8mb4;

-- 9053 是已经存在的节点侧对称密钥页面，只是上一轮被隐藏且漏授 role=2。
UPDATE sys_menu
SET parent_id = 9420, order_num = 6, menu_name = '已分发对称密钥',
    path = 'symkeys', component = 'distribute/symmetricKeys', visible = '0',
    menu_type = 'C', is_frame = 1
WHERE menu_id = 9053;

INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (2, 9053)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- 分析详情归到节点侧「密钥生成」，管理员只保留汇总监管能力。
UPDATE sys_menu
SET parent_id = 9400, order_num = 3, menu_name = '一致性与异常分析', visible = '0'
WHERE menu_id = 9412;

UPDATE sys_menu
SET parent_id = 9400, order_num = 4, menu_name = '泄漏关联分析', visible = '0'
WHERE menu_id = 9413;

INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (2, 9412), (2, 9413)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

DELETE FROM sys_role_menu
WHERE role_id = 1 AND menu_id IN (9412, 9413);

-- 验收测试台是管理端唯一的量化/验收入口，确保仍可见且有管理员授权。
UPDATE sys_menu
SET parent_id = 0, menu_type = 'C', is_frame = 1, visible = '0',
    menu_name = '验收测试台', path = 'acceptance', component = 'frame/index'
WHERE menu_id = 9201;

INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9201)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);
