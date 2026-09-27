-- =============================================================================
-- 29_distribution_native_pages.sql
-- -----------------------------------------------------------------------------
-- 把「分发与区块链」这一组从 **iframe 嵌分发模块** 换成 **管理端原生页面**。
--
-- 背景（用户 2026-09-24 反馈，有截图）
-- -----------------------------------
-- 原配置：
--   9101 分发控制台   → frame/index + query=/distribute/
--   9102 区块链浏览器 → frame/index + query=/distribute/#/blockchain
-- 这两项点开渲染出来的是**分发模块自带应用的登录页**（"抗量子分发系统 欢迎您！"），
-- 因为 django-vue3-admin 有自己的一套登录态，与管理端是两套。用户要的不是
-- "跳去另一个系统的登录页"，而是**把分发功能复用到管理端里**。
--
-- 改法：只复用它的**功能与数据**（接口 `/pqkds-api/*` 本来就是开放的），
-- 页面全部用管理端自己的组件与登录态重写：
--
--   组件                              | 干什么
--   ----------------------------------|------------------------------------------
--   distOverview/index  「分发总览」   | 节点/密钥池/会话/日志的聚合视图 + 快速入口
--   keypool/index       「密钥池」     | 预分配密钥：查看、生成并分发、补充、清理、删除
--   sessions/index      「会话密钥」   | 节点间会话的元数据（只读，密文不下发）
--   distlogs/index      「分发日志」   | 节点侧密钥动作流水（含链上交易哈希）
--   chain/index         「区块链存证」 | 密钥生命周期在 FISCO 链上的 tx 哈希与块高
--   nodes/index         「节点管理」   | 演示节点的增删改（上一轮已完成）
--
-- 注意「区块链存证」与原「区块链浏览器」的口径差别：原页面是分发模块自带视图，
-- 默认 provider 是 **Ganache**（`http://127.0.0.1:7545`），与 KMS 实际使用的
-- FISCO 链不是一条链；现在改成展示**本系统真正写进 FISCO 的存证**。
--
-- 幂等：ON DUPLICATE KEY UPDATE。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 两个 iframe 菜单改成原生组件（query 必须清空，否则 frame 组件的残留地址会误导排查）
-- ---------------------------------------------------------------------------
UPDATE sys_menu
SET menu_name = '分发总览', path = 'overview', component = 'distOverview/index',
    query = '', is_frame = 0, order_num = 1,
    remark = '分发模块功能的管理端原生聚合页（不再 iframe 嵌它的控制台）'
WHERE menu_id = 9101;

UPDATE sys_menu
SET menu_name = '区块链存证', path = 'chain', component = 'chain/index',
    query = '', is_frame = 0, order_num = 5,
    remark = '密钥生命周期在 FISCO 链上的存证（tx 哈希 + 块高），非 Ganache 口径'
WHERE menu_id = 9102;

-- 节点管理顺位后移，排在这组最后
UPDATE sys_menu SET order_num = 6 WHERE menu_id = 9103;

-- ---------------------------------------------------------------------------
-- 2. 新增三个分发功能页
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9104, '密钥池', 9100, 2, 'keypool', 'keypool/index', 0, 0,
        'C', '0', '0', 'pqkds:keypool:view', 'component', 'admin', NOW(),
        '预分配密钥池：生成并分发、补充、清理过期、删除')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        order_num = VALUES(order_num), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9105, '会话密钥', 9100, 3, 'sessions', 'sessions/index', 0, 0,
        'C', '0', '0', 'pqkds:session:view', 'message', 'admin', NOW(),
        '节点间会话密钥的元数据（只读；密文不下发浏览器）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        order_num = VALUES(order_num), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9106, '分发日志', 9100, 4, 'distlogs', 'distlogs/index', 0, 0,
        'C', '0', '0', 'pqkds:distlog:view', 'log', 'admin', NOW(),
        '节点侧密钥动作流水（部分密钥生成/上链存储/更新/撤销）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        path = VALUES(path), component = VALUES(component),
                        order_num = VALUES(order_num), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 3. 角色映射（只插菜单不插映射 → 侧边栏里看不到，是个很容易漏的坑）
-- ---------------------------------------------------------------------------
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9101), (1, 9102), (1, 9103), (1, 9104), (1, 9105), (1, 9106)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

SELECT '分发与区块链菜单' AS check_item, menu_id, menu_name, path, component, order_num
FROM sys_menu WHERE parent_id = 9100 ORDER BY order_num;