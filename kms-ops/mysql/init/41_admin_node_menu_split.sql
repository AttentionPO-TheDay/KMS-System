-- =============================================================================
-- 41_admin_node_menu_split.sql
-- -----------------------------------------------------------------------------
-- 按 doc/admin-node-login-design.md §9/§10/§11 把侧边栏拆成**管理端**与**节点端**
-- 两棵独立的树。
--
-- 问题（用户反馈）
-- ----------------
-- 「每个子系统进去后侧边栏应该是该系统的功能，目前进去后就是一个公共的侧边栏」。
--
-- 核实结论：侧边栏只有唯一来源 sys_menu → /getRouters → permission.js → Sidebar。
-- 后端 `buildMenus` **不区分登录主体**，只按 sys_role_menu 取菜单。所以此前
-- ADMIN 与 NODE 看到的是同一棵树 —— 36_*.sql 排的是「三子系统 + 综合管理」四区，
-- 既不是 §11.1 的管理端结构，也不是 §11.2 的节点端结构，且四区里管理监管页
-- 与节点自助页混在一起。
--
-- 做法
-- ----
-- **不改后端**，靠 sys_role_menu 把同一批菜单行按角色分叉：
--   role_id=1（管理员）→ 管理端树
--   role_id=2（节点）  → 节点端树
-- 复用既有 menu_id 只改 parent_id / order_num / visible / 必要时改 path，
-- 不新建重复菜单。
--
-- ⚠️ 三条硬约束（都是本仓库踩过的坑，务必保留）
-- ------------------------------------------------------------
-- 【一】子菜单 path 必须**全局唯一**
--   后端 `SysMenuServiceImpl.getRouteName()` 生成路由名 = capitalize(path)，
--   而 vue-router 4 在 addRoute 遇到重名时会**先移除旧路由**。
--   36/38/39 号脚本的注释里都记录过这个坑。
--   本脚本因此把 9006（节点鉴权）的 path 从 `index` 改成 `authlist`：
--   `index` 与静态路由的仪表盘同名，是一个**潜伏的重名源**。
--
-- 【二】顶层 menu_type='C' 必须 is_frame=1
--   `UserConstants.YES_FRAME="0"`（是外链）/ `NO_FRAME="1"`（不是外链），
--   `isMenuFrame()` 要求 isFrame == NO_FRAME 即 **1**。
--   写成 0 的后果不是"退化成普通菜单"，而是**整站登录后卡死**（详见 30_*.sql）。
--
-- 【三】必须带 SET NAMES utf8mb4
--   管道导入时客户端字符集不保证是 utf8mb4，缺了会双重编码（30_*.sql 踩过，
--   由 37_*.sql 修复）。
--
-- 本脚本**不制造死菜单**：所有挂上去的菜单，其 component 对应的 .vue 页面
-- 在本轮一并补齐（见下方 NODE/ADMIN 各段的 NEW 标注）。
--
-- 幂等：全部为 UPDATE / INSERT ... ON DUPLICATE KEY UPDATE / 按条件的 DELETE。
-- =============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 0. 新建四个顶层目录 + 一个顶层页面
-- ---------------------------------------------------------------------------
-- 顶部对齐 §11：管理端四个分区；节点端沿用 9400/9410/9420 并把 9430 改造成「节点信息」。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9440, '密钥生成监管',       0, 10, 'reggov',   NULL, 1, 0, 'M', '0', '0', '', 'form',    'admin', NOW(), '§11.1 管理端分区一：生成侧的监管视图'),
 (9450, '密钥更新与回收监管', 0, 20, 'lifegov',  NULL, 1, 0, 'M', '0', '0', '', 'refresh', 'admin', NOW(), '§11.1 管理端分区二：存续/轮换/终止侧的监管视图'),
 (9460, '密钥分发监管',       0, 30, 'distgov',  NULL, 1, 0, 'M', '0', '0', '', 'share',   'admin', NOW(), '§11.1 管理端分区三：使用与短期会话侧的监管视图'),
 (9470, '节点管理',           0, 40, 'nodegov',  NULL, 1, 0, 'M', '0', '0', '', 'tree',    'admin', NOW(), '§9.2 管理端：节点列表/节点授权/域管理'),
 (9430, '节点信息',           0, 10, 'selfzone', NULL, 1, 0, 'M', '0', '0', '', 'user',    'admin', NOW(), '§11.2 节点端：当前节点/本地密钥环境/我的日志')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        menu_type = VALUES(menu_type), icon = VALUES(icon),
                        remark = VALUES(remark);

-- 系统总览：顶层页面（§11.1 第一个条目）。
--
-- ⚠️ path 取 `console` 而不是 `index`/`dashboard`：两者都会撞路由名 ——
--    `index` 被 9006 占用（本脚本会改掉，但静态仪表盘路由仍叫 Dashboard），
--    `dashboard` 会生成 name=`Dashboard`，与静态路由重名后被 vue-router 顶掉。
--    component 仍指向 views/index.vue。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9260, '系统总览', 0, 1, 'console', 'index', 1, 0,
        'C', '0', '0', '', 'dashboard', 'admin', NOW(),
        '§9.1 管理端：节点/密钥/会话/预分配池/异常事件总览')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        is_frame = VALUES(is_frame), icon = VALUES(icon), remark = VALUES(remark);

-- ===========================================================================
-- 1. 管理端 · 密钥生成监管（9440）
-- ===========================================================================
-- 生成统计 / 节点初始化状态为**新页面**（views/generateStats、views/nodeInitStatus）。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9441, '生成统计',       9440, 1, 'genstats',   'generateStats/index',  1, 0, 'C', '0', '0', '', 'chart', 'admin', NOW(), 'NEW：生成量按算法/节点/时间聚合'),
 (9442, '节点初始化状态', 9440, 2, 'initstatus', 'nodeInitStatus/index', 1, 0, 'C', '0', '0', '', 'lock',  'admin', NOW(), 'NEW：各节点 PENDING_INIT/ACTIVE/DISABLED 与四套公钥就绪情况')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon), remark = VALUES(remark);

-- 密钥查询：复用 9021（原「用户密钥查询」，component query/keyList/index ——
-- 本就是全库维度查询，属监管视角，不需要新页面，只改名并归位）。
UPDATE sys_menu SET parent_id = 9440, order_num = 3, menu_name = '密钥查询' WHERE menu_id = 9021;

-- ===========================================================================
-- 2. 管理端 · 密钥更新与回收监管（9450）
-- ===========================================================================
-- 更新状态 / 异常密钥为**新页面**（views/updateStatus、views/abnormalKeys）。
--
-- ⚠️ 更新状态**没有**新建页面文件：它复用既有的 views/keyautoupdate/index.vue
--    （该页本就是"列出全部密钥 + 版本/自动更新/状态"的列表，§11.1 要的
--     轮换进度就是它），只改菜单名与挂载点。少一个页面就少一处要同步维护
--     的同一份列表。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9451, '更新状态',   9450, 1, 'updstats', 'keyautoupdate/index', 1, 0, 'C', '0', '0', '', 'time-range', 'admin', NOW(), '§11.1 轮换进度与版本分布（复用既有 keyautoupdate 页）'),
 (9452, '异常密钥',   9450, 2, 'badkeys',  'abnormalKeys/index', 1, 0, 'C', '0', '0', '', 'warning',    'admin', NOW(), 'NEW：异常密钥列表与处置入口（列表视角）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon), remark = VALUES(remark);

-- 一致性检查 / 泄漏关联分析：复用 9412、9413（页面已存在）。
-- 与「异常密钥」的分工：异常密钥是**列表 + 批量处置**，一致性检查是**单钥诊断**。
UPDATE sys_menu SET parent_id = 9450, order_num = 3, menu_name = '一致性检查' WHERE menu_id = 9412;
UPDATE sys_menu SET parent_id = 9450, order_num = 4 WHERE menu_id = 9413;

-- ===========================================================================
-- 3. 管理端 · 密钥分发监管（9460）
-- ===========================================================================
-- 分发总览 / 会话监控：复用 9101、9105（页面已存在），只改名归位。
UPDATE sys_menu SET parent_id = 9460, order_num = 1, menu_name = '分发总览' WHERE menu_id = 9101;
UPDATE sys_menu SET parent_id = 9460, order_num = 3, menu_name = '会话监控' WHERE menu_id = 9105;

-- 跨域分发为新页面（views/crossDomain）。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9453, '跨域分发', 9460, 4, 'crossdom', 'crossDomain/index', 1, 0,
        'C', '0', '0', '', 'international', 'admin', NOW(),
        'NEW：同域/跨域分发对照（读 source_domain_id / target_domain_ids）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 3.5 ⚠️ 「预分配密钥池」必须换 path —— 否则与节点端「密钥池」撞路由名
-- ---------------------------------------------------------------------------
-- 9104 原 path='keypool'（name=Keypool），节点端 §11.2 也要一个「密钥池」。
-- 两者若都叫 keypool，vue-router 会先移除旧路由，表现为**其中一个菜单点不开**。
-- 因此：
--   9104 → path 改为 `poolgov`，component 指向新建的只读监管页 keypool/overview
--   节点端「密钥池」(9472) 独占 `selfpool`，component 复用 keypool/index
UPDATE sys_menu
SET parent_id = 9460, order_num = 2,
    menu_name = '预分配密钥池', path = 'poolgov', component = 'keypool/overview', is_frame = 0,
    remark = '§9.8 管理端只读视图：池容量/READY/RESERVED/CONSUMED/EXPIRED/REVOKED'
WHERE menu_id = 9104;

-- ===========================================================================
-- 4. 管理端 · 节点管理（9470）
-- ===========================================================================
UPDATE sys_menu SET parent_id = 9470, order_num = 1, menu_name = '节点列表' WHERE menu_id = 9103;
UPDATE sys_menu SET parent_id = 9470, order_num = 2, menu_name = '节点授权' WHERE menu_id = 9005;

-- 9006 的 path 从 `index` 改为 `authlist`：
-- `index` 会生成路由名 `Index`，与静态仪表盘路由（name=Dashboard, path=/index）
-- 属于同一命名空间的潜伏冲突源。此改动同时为将来任何 path='index' 的菜单让路。
UPDATE sys_menu SET path = 'authlist', menu_name = '节点授权' WHERE menu_id = 9006;

-- 域管理为新页面（views/domains）。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9461, '域管理', 9470, 3, 'domains', 'domains/index', 1, 0,
        'C', '0', '0', '', 'international', 'admin', NOW(),
        'NEW：§9.10 域列表 + 各域节点分布（读 Node.domain_id）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon), remark = VALUES(remark);

-- ===========================================================================
-- 5. 管理端 · 顶层页面（区块链存证 / 操作日志 / 验收测试）
-- ===========================================================================
-- 区块链存证：9102 由 29_*.sql 改成原生页 chain/index，这里升为顶层。
-- path 由 `chain` 改为 `chainproof`：`chain` 本身不冲突，但顶层 C 与子级 C 用
-- 同一个 path 会让"它在树里哪一层"变得难读，改名更明确。
UPDATE sys_menu
SET parent_id = 0, menu_type = 'C', is_frame = 1, order_num = 50,
    menu_name = '区块链存证', path = 'chainproof', component = 'chain/index', query = '', perms = ''
WHERE menu_id = 9102;

-- 操作日志：新建顶层页面，复用既有 500（monitor/operlog/index）。
-- 不复用 108「日志审计」目录：§11.1 把「操作日志」直接列在顶层。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9280, '操作日志', 0, 60, 'auditlog', 'monitor/operlog/index', 1, 0,
        'C', '0', '0', 'monitor:operlog:list', 'form', 'admin', NOW(),
        '§9.12 管理端：管理员与节点的关键操作流水')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        is_frame = VALUES(is_frame), perms = VALUES(perms),
                        icon = VALUES(icon), remark = VALUES(remark);

-- 验收测试台：9201 升为顶层（原来是 9200「测试」下的子项）。
-- is_frame 必须改成 1（顶层 C 的要求，见文件头约束二）。
UPDATE sys_menu
SET parent_id = 0, menu_type = 'C', is_frame = 1, order_num = 70,
    menu_name = '验收测试台'
WHERE menu_id = 9201;

-- ===========================================================================
-- 6. 节点端 · 三棵业务子树（9400 / 9410 / 9420）
-- ===========================================================================
UPDATE sys_menu SET menu_name = '密钥生成',   parent_id = 0, order_num = 20 WHERE menu_id = 9400;
UPDATE sys_menu SET menu_name = '更新与回收', parent_id = 0, order_num = 30 WHERE menu_id = 9410;
UPDATE sys_menu SET menu_name = '密钥分发',   parent_id = 0, order_num = 40 WHERE menu_id = 9420;

-- --- 密钥生成 ---
UPDATE sys_menu SET parent_id = 9400, order_num = 1 WHERE menu_id = 9054;  -- 生成密钥
UPDATE sys_menu SET parent_id = 9400, order_num = 2 WHERE menu_id = 9011;  -- 生成历史

-- --- 更新与回收 ---
-- 我的密钥：复用 9023 的**既有页面** views/userKeys/index.vue。
-- 该页本来就只显示当前用户自己的密钥（getUserProfile() 取到 userId 后
-- 写进 queryParams 再查 listKeymanage，见该文件约 342-352 行），
-- 且第一个页签就叫「我的密钥」—— 它就是 §11.2 要的那一页，
-- 不需要（也不应该）另建一个同名页面。这里只改菜单名与归属。
UPDATE sys_menu
SET parent_id = 9410, order_num = 1, menu_name = '我的密钥', component = 'userKeys/index'
WHERE menu_id = 9023;
UPDATE sys_menu SET parent_id = 9410, order_num = 2 WHERE menu_id = 5000;  -- 密钥更新
UPDATE sys_menu SET parent_id = 9410, order_num = 3 WHERE menu_id = 9411;  -- 版本历史
UPDATE sys_menu SET parent_id = 9410, order_num = 4 WHERE menu_id = 7000;  -- 密钥回收

-- --- 密钥分发 ---
UPDATE sys_menu SET parent_id = 9420, order_num = 1, menu_name = '发起分发' WHERE menu_id = 9052;
UPDATE sys_menu SET parent_id = 9420, order_num = 5, menu_name = '分发记录' WHERE menu_id = 9106;

-- 预分配 / 密钥池 / 会话管理：三个新页面。
-- 「预分配」与「密钥池」的区别（§10.8 / §10.9）：
--   预分配 = 动作（为指定节点对准备 N 条、指定算法与 TTL）
--   密钥池 = 资源（那批已备好的 SM4 资源及其 READY/RESERVED/... 状态）
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9471, '预分配',   9420, 2, 'prealloc',  'preallocate/index',  1, 0, 'C', '0', '0', '', 'clock',   'admin', NOW(), 'NEW：§10.8 为指定节点对提前准备短期会话密钥'),
 (9472, '密钥池',   9420, 3, 'selfpool',  'keypool/index',      1, 0, 'C', '0', '0', '', 'key',     'admin', NOW(), 'NEW：§10.9 本节点尚未被会话消费的预分配密钥资源'),
 (9473, '会话管理', 9420, 4, 'selfsess',  'selfSessions/index', 1, 0, 'C', '0', '0', '', 'message', 'admin', NOW(), 'NEW：§10.10 本节点参与的分发会话（含 Falcon 签名状态）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon), remark = VALUES(remark);

-- ===========================================================================
-- 7. 节点端 · 节点信息（9430）
-- ===========================================================================
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9474, '当前节点',     9430, 1, 'selfnode', 'selfNode/index', 1, 0, 'C', '0', '0', '', 'user', 'admin', NOW(), 'NEW：§10.1 节点名称/类型/权限等级/所属域/初始化状态'),
 (9475, '本地密钥环境', 9430, 2, 'keystore', 'keyStore/index', 1, 0, 'C', '0', '0', '', 'lock', 'admin', NOW(), 'NEW：§10.2 NodeKeyStore / Device Credential / 四套密钥存在状态（不展示私钥）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), icon = VALUES(icon), remark = VALUES(remark);

UPDATE sys_menu SET parent_id = 9430, order_num = 3, menu_name = '我的日志' WHERE menu_id = 9051;

-- 工作台保持顶层（§11.2 第一个条目），归节点端。
UPDATE sys_menu SET parent_id = 0, order_num = 5, menu_name = '工作台' WHERE menu_id = 9050;

-- ===========================================================================
-- 8. 隐藏：文档 §11 未列出的历史页面
-- ===========================================================================
-- ⚠️ 只设 visible='1'，**不删除** —— sys_menu 是侧边栏的唯一来源，删行会连带
--    弄坏授权与历史引用。页面文件保留在磁盘上，将来要复用时改回 '0' 即可。
--
-- 逐项理由：
--   9001/9002/9004  旧顶层目录，成员已全部迁走，留着是空分组
--   9003            算法说明目录（成员 9031/9032/9033 一并隐藏）
--   9053 对称密钥   演示页，§11.2 未列
--   9012 公共参数   技术页，§9.3 明确"不再占据核心菜单"
--   9022 公钥查询 / 9024 密钥用户管理  §11.1 的密钥查询已由 9021 承担
--   9100 分发与区块链 旧目录，成员已迁出
--   9200 测试       目录已空（唯一成员 9201 已升为顶层）
--   9431 安全监控   与 §11.1 的「分发总览」语义重叠，§11 未列
--   6000 密钥自动更新 §11.2 更新与回收下只列了四个页面，不含自动更新
UPDATE sys_menu SET visible = '1'
WHERE menu_id IN (9001, 9002, 9003, 9004, 9012, 9022, 9024, 9031, 9032, 9033,
                  9053, 9100, 9200, 9431, 6000);

-- ===========================================================================
-- 9. 授权分叉
-- ===========================================================================
-- ⚠️ 用事务包住"先清后设"。
--    清空 sys_role_menu 到重新插入之间若中断，用户会**失去全部菜单** ——
--    侧边栏整个空掉，且因为 sys_menu 还在，排查时很容易往错的方向找。
--    本脚本约定用 `mysql --default-character-set=utf8mb4 < 41_*.sql` 单连接执行，
--    不经过任何会按语句切分的中间层；DDL 已在文件外的建表阶段完成，
--    这里全是 DML，可以安全地放进一个事务。
START TRANSACTION;

-- 不做增量对账，而是**先清后设**：结果完全由本脚本决定。
-- 只清本脚本负责的两个角色（1 管理员 / 2 节点），其它角色不受影响。
DELETE FROM sys_role_menu WHERE role_id IN (1, 2);

-- --- role 1（管理员）→ 管理端整棵树 ---
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, menu_id FROM sys_menu
WHERE menu_id IN (9260, 9440, 9441, 9442, 9021,
                        9450, 9451, 9452, 9412, 9413,
                        9460, 9101, 9104, 9105, 9453,
                        9470, 9103, 9005, 9006, 9461,
                        9102, 9280, 9201)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- --- role 2（节点）→ 节点端整棵树 ---
-- ⚠️ 节点**不得**拿到 9005/9006（节点授权）/ 9103（节点管理）等管理页。
--    40_*.sql 曾因"孤儿页面补祖先"把这些目录一起补给了 role 2，
--    本脚本的显式列表把它收回。后端按权限串放行，这些授权是真实可达的能力，
--    不是"菜单看不见而已"（32_*.sql 的实测记录）。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 2, menu_id FROM sys_menu
WHERE menu_id IN (9050,
                  9400, 9054, 9011,
                  9410, 9023, 5000, 9411, 7000,
                  9420, 9052, 9471, 9472, 9473, 9106,
                  9430, 9474, 9475, 9051)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- 按钮级(F)授权跟随其父菜单：5000/6000/7000 下的 2003/2004/2005。
-- 6000 已隐藏，其按钮 2004 一并收回。
DELETE rm FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE rm.role_id = 2 AND m.menu_id IN (2003, 2004, 2005);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 2, menu_id FROM sys_menu
WHERE menu_id IN (2003, 2005)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

COMMIT;

-- ===========================================================================
-- 10. 自检
-- ===========================================================================
SELECT '路由名冲突（应为空）' AS check_item, LOWER(path) AS colliding_path, COUNT(*) AS cnt
FROM sys_menu
WHERE status = '0' AND visible = '0' AND menu_type IN ('M', 'C')
GROUP BY LOWER(path) HAVING COUNT(*) > 1;

SELECT '管理端侧边栏（role 1）' AS check_item,
       COALESCE(NULLIF(p.menu_name, ''), '（顶层）') AS zone,
       c.menu_id, c.menu_name, c.path, c.component, c.order_num
FROM sys_role_menu rm
JOIN sys_menu c ON c.menu_id = rm.menu_id
LEFT JOIN sys_menu p ON p.menu_id = c.parent_id
WHERE rm.role_id = 1 AND c.visible = '0' AND c.menu_type IN ('M', 'C')
ORDER BY COALESCE(p.order_num, c.order_num), c.parent_id, c.order_num;

SELECT '节点端侧边栏（role 2）' AS check_item,
       COALESCE(NULLIF(p.menu_name, ''), '（顶层）') AS zone,
       c.menu_id, c.menu_name, c.path, c.component, c.order_num
FROM sys_role_menu rm
JOIN sys_menu c ON c.menu_id = rm.menu_id
LEFT JOIN sys_menu p ON p.menu_id = c.parent_id
WHERE rm.role_id = 2 AND c.visible = '0' AND c.menu_type IN ('M', 'C')
ORDER BY COALESCE(p.order_num, c.order_num), c.parent_id, c.order_num;

-- 关键断言：role 2 **不得**残留任何管理类权限串。期望为空集。
SELECT 'role=2 残留管理权限（应为空）' AS check_item, m.menu_id, m.menu_name, m.perms
FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE rm.role_id = 2
  AND (m.perms LIKE 'system:%' OR m.perms LIKE 'monitor:%' OR m.menu_id IN (9005, 9006, 9103, 9102));

-- 挂上去的每个 component 都必须有对应页面文件，否则点开就是 404。
SELECT '菜单组件清单（供逐个核对 .vue 是否存在）' AS check_item, menu_id, menu_name, component
FROM sys_menu
WHERE visible = '0' AND status = '0' AND menu_type = 'C' AND component NOT LIKE 'monitor/%'
ORDER BY parent_id, order_num;

-- 静默失败检查：目录下的成员若全被隐藏，该目录会变成"点开没内容"的空壳。
SELECT '空壳目录（应为空）' AS check_item, p.menu_id, p.menu_name
FROM sys_menu p
WHERE p.menu_type = 'M' AND p.visible = '0'
  AND NOT EXISTS (
      SELECT 1 FROM (SELECT parent_id FROM sys_menu WHERE visible = '0' AND status = '0') AS c
      WHERE c.parent_id = p.menu_id
  );
