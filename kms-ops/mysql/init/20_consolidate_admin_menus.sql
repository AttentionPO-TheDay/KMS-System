-- =============================================================================
-- 20_consolidate_admin_menus.sql
-- -----------------------------------------------------------------------------
-- 目的：把管理端菜单整理成「分组 + 子项」的结构，并清理无效菜单。
--
-- 解决的问题：
--   1. 菜单平铺：8 个一级菜单并列，没有分组，功能多了以后无法扫读。
--   2. 存在 component 指向**不存在的页面**的菜单，点击后是白页：
--        keyuser/keyuser/index  （用户管理）
--        keygenerate/index      （密钥生成，实际文件是 generate/index）
--        blockchain/index       （区块链查看）
--        tool/build|gen|swagger （表单构建/代码生成/系统接口）
--   3. 重复菜单：8001「权限审批」与 8006「Permission Approval」、
--      8002「权限申请」与 8007「Permission Request」指向同一组件。
--
-- 设计：
--   - 只保留「确实存在对应页面」的菜单，其余删除。
--   - 用 menu_type='M' 的分组节点组织子菜单，侧边栏即呈现为菜单栏结构。
--   - 已有且正确的菜单（系统管理/日志/密钥更新等）保留原 id，
--     以免破坏 sys_role_menu 中非管理员角色的既有授权。
--
-- 幂等：脚本先删除本脚本要重建的菜单，再插入，可重复执行。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 删除指向不存在页面的菜单（及其按钮级子项）
-- ---------------------------------------------------------------------------
-- 用户管理（keyuser）：页面不存在，实际由「密钥用户管理」承担
-- ⚠️ 必须有这一行（2026-09-30 补）：本文件含中文，而**管道导入**
--    （docker-entrypoint-initdb.d / docker exec -i ... mysql < file）时
--    客户端字符集不保证是 utf8mb4。缺了它中文会按单字节解析后再以 utf8mb4 存储，
--    即**双重编码** —— 库里存的是 C3A5C2B7... 这类字节，前端渲染成「å·¥ä½œå°」。
--    本文件此前正因缺这一行，把 20 个菜单名写坏（由 42_*.sql 修复）。
SET NAMES utf8mb4;

DELETE FROM sys_role_menu WHERE menu_id IN (3000, 3001, 3002, 3003, 3004, 3005);
DELETE FROM sys_menu      WHERE menu_id IN (3000, 3001, 3002, 3003, 3004, 3005);

-- 区块链查看：页面不存在
DELETE FROM sys_role_menu WHERE menu_id = 8000;
DELETE FROM sys_menu      WHERE menu_id = 8000;

-- 英文重复菜单：与 8001/8002 同路径同组件，删除
DELETE FROM sys_role_menu WHERE menu_id IN (8006, 8007, 8008, 8009);
DELETE FROM sys_menu      WHERE menu_id IN (8006, 8007, 8008, 8009);

-- 系统工具（表单构建/代码生成/系统接口）：页面不存在，连同按钮级子项删除
DELETE FROM sys_role_menu WHERE menu_id IN (115, 116, 117, 1055, 1056, 1057, 1058, 1059, 1060);
DELETE FROM sys_menu      WHERE menu_id IN (115, 116, 117, 1055, 1056, 1057, 1058, 1059, 1060);
DELETE FROM sys_role_menu WHERE menu_id = 5;
DELETE FROM sys_menu      WHERE menu_id = 5;

-- 修正密钥生成的组件路径（原为不存在的 keygenerate/index）
UPDATE sys_menu SET component = 'generate/index', path = 'generate'
WHERE menu_id = 4000;

-- ---------------------------------------------------------------------------
-- 2. 新增分组节点（menu_type='M'，不带 component 时 RuoYi 会渲染为可展开分组）
--    使用 9000+ 段，避免与既有 id 冲突
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
  (9001, '密钥管理', 0, 10, 'key',        NULL, 1, 0, 'M', '0', '0', '', 'lock',       'admin', NOW(), '密钥生成 / 更新 / 回收 等操作入口'),
  (9002, '密钥查询', 0, 20, 'query',      NULL, 1, 0, 'M', '0', '0', '', 'search',     'admin', NOW(), '按用户、公钥等维度查询密钥'),
  (9003, '算法说明', 0, 30, 'algorithm',  NULL, 1, 0, 'M', '0', '0', '', 'guide',      'admin', NOW(), '无证书算法原理与轮换过程演示'),
  (9004, '权限与审计', 0, 40, 'audit',    NULL, 1, 0, 'M', '0', '0', '', 'peoples',    'admin', NOW(), '权限审批与操作/登录日志')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
  order_num = VALUES(order_num), path = VALUES(path), icon = VALUES(icon), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 3. 把既有业务菜单挂到分组下，并调整顺序
-- ---------------------------------------------------------------------------
UPDATE sys_menu SET parent_id = 9001, order_num = 1 WHERE menu_id = 4000;  -- 密钥生成
UPDATE sys_menu SET parent_id = 9001, order_num = 4 WHERE menu_id = 5000;  -- 密钥更新
UPDATE sys_menu SET parent_id = 9001, order_num = 5 WHERE menu_id = 7000;  -- 密钥回收
UPDATE sys_menu SET parent_id = 9001, order_num = 6 WHERE menu_id = 6000;  -- 密钥自动更新

UPDATE sys_menu SET parent_id = 9004, order_num = 1 WHERE menu_id = 8001;  -- 权限审批
UPDATE sys_menu SET parent_id = 9004, order_num = 2 WHERE menu_id = 108;   -- 日志审计（其下含操作/登录日志）
UPDATE sys_menu SET parent_id = 0,    order_num = 90 WHERE menu_id = 4;    -- 系统管理保持在末位

-- 权限申请（8002）的按钮级子项顺序不动

-- ---------------------------------------------------------------------------
-- 4. 新增缺失的业务菜单（页面均已存在）
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
  -- 密钥管理
  (9011, '生成历史',   9001, 2, 'history',       'generateHistory/index',      1, 0, 'C', '0', '0', '', 'chart',  'admin', NOW(), '历史生成记录'),
  (9012, '公共参数',   9001, 3, 'common-param',  'commonParam/index',          1, 0, 'C', '0', '0', '', 'list',   'admin', NOW(), '系统公共参数查询'),
  -- 密钥查询
  (9021, '用户密钥查询', 9002, 1, 'key-list',       'query/keyList/index',      1, 0, 'C', '0', '0', '', 'list',    'admin', NOW(), '按用户维度查询密钥'),
  (9022, '公钥查询',     9002, 2, 'public-keys',    'publickeys/index',         1, 0, 'C', '0', '0', '', 'lock',    'admin', NOW(), '公共密钥列表'),
  (9023, '用户密钥池',   9002, 3, 'user-keys',      'userKeys/index',           1, 0, 'C', '0', '0', '', 'key',     'admin', NOW(), '用户侧密钥池视图'),
  (9024, '密钥用户管理', 9002, 4, 'business-users', 'query/businessUsers/index',1, 0, 'C', '0', '0', '', 'peoples', 'admin', NOW(), '业务用户与密钥归属'),
  -- 算法说明
  (9031, '算法图解与演示', 9003, 1, 'demo',    'algorithm/index',       1, 0, 'C', '0', '0', '', 'guide',     'admin', NOW(), 'SM2/SSCL 与抗量子算法图解'),
  (9032, '更新回收速览',   9003, 2, 'quick',   'algorithm/quickView',   1, 0, 'C', '0', '0', '', 'guide',     'admin', NOW(), '更新与回收算法速览'),
  (9033, '轮换计算揭秘',   9003, 3, 'process', 'algorithm/processView', 1, 0, 'C', '0', '0', '', 'data-line', 'admin', NOW(), '密钥轮换的分步计算过程'),
  -- 系统管理补齐（页面已存在但菜单缺失）
  (9041, '菜单管理', 4, 3, 'menu',   'system/menu/index',   1, 0, 'C', '0', '0', '', 'tree-table', 'admin', NOW(), '菜单与权限标识维护'),
  (9042, '部门管理', 4, 4, 'dept',   'system/dept/index',   1, 0, 'C', '0', '0', '', 'tree',       'admin', NOW(), '组织架构维护'),
  (9043, '字典管理', 4, 5, 'dict',   'system/dict/index',   1, 0, 'C', '0', '0', '', 'dict',       'admin', NOW(), '数据字典维护'),
  (9044, '参数设置', 4, 6, 'config', 'system/config/index', 1, 0, 'C', '0', '0', '', 'edit',       'admin', NOW(), '系统参数维护'),
  (9045, '通知公告', 4, 7, 'notice', 'system/notice/index', 1, 0, 'C', '0', '0', '', 'message',    'admin', NOW(), '站内通知公告'),
  (9046, '岗位管理', 4, 8, 'post',   'system/post/index',   1, 0, 'C', '0', '0', '', 'post',       'admin', NOW(), '岗位维护')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
  order_num = VALUES(order_num), path = VALUES(path), component = VALUES(component),
  icon = VALUES(icon), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 5. 把新增菜单授权给管理员角色（role_id=1）
--    说明：admin 账号本身走超管豁免，不受 role_menu 限制；
--    这里补授权是为了其他拥有 admin 角色的账号也能看到。
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT 1, menu_id FROM sys_menu
WHERE menu_id IN (9001, 9002, 9003, 9004, 9011, 9012, 9021, 9022, 9023, 9024, 9031, 9032, 9033, 9041, 9042, 9043, 9044, 9045, 9046);
