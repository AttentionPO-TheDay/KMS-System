-- =============================================================================
-- 30_port_user_pages_into_console.sql
-- -----------------------------------------------------------------------------
-- 阶段 1（前端合并）配套菜单：把自 `kms-user/front` 迁入主控制台的业务页
-- 接入 `sys_menu`，使其经 `/getRouters` 下发、由 `permission.js` 的 `loadView`
-- 解析成动态路由。
--
-- 为什么必须有这一步
-- ----------------
-- 本控制台的业务路由**全部**由 `sys_menu` 驱动（见 `src/router/index.js` 开头的
-- 约定：业务页只留 `sys_menu` 一个来源）。只把 .vue 文件拷进来、不插菜单行，
-- 页面就**不可达**；再叠加阶段 1 已停止构建 `kms-user/front`，这些能力会直接消失。
-- 所以菜单接入是阶段 1 的一部分，不是阶段 9 的提前动作。
--
-- ⚠️ 与阶段 9 的关系
-- ------------------
-- 阶段 9 会**重建** `sys_menu`（按文档 §9.3 的三子系统 + 综合管理分组）。
-- 本脚本给的是**过渡期**结构，阶段 9 重建时应当把它整体替换掉。
--
-- =============================================================================
-- 两个必须遵守的约束（都来自对 RuoYi 后端源码的核实，不是惯例猜测）
-- =============================================================================
--
-- 【约束一】menu_id 必须避开已用区间
--   本仓库已占用的 9xxx 区间（经全量 grep 核实）：
--     9000–9006、9011–9016、9021–9024、9031–9033、9041–9046、9100–9106、9200–9201
--   其中 9001–9004 是 20 号脚本建立的**在用顶层分组**，9005/9006 是 25 号的节点鉴权，
--   9011/9012 已分别被「生成历史」「公共参数」占用。
--   本脚本因此从 **9050** 起用全新区间，不触碰任何既有 ID。
--
-- 【约束二】子级菜单的 `path` 必须全局唯一 —— 否则路由会被静默顶掉
--   路由名由后端 `SysMenuServiceImpl.getRouteName()` 生成：
--       return StringUtils.capitalize(menu.getRouteName() != null ? ... : menu.getPath());
--   即 **name = 首字母大写的 path**（`capitalize` 只改首字符，其余保持原样）。
--   而 vue-router 4 在 `addRoute` 遇到**重名**时会**先移除旧路由**。
--   现存菜单里已经有一个 path='index' 的子菜单（9006 节点鉴权），
--   若本轮再挂 path='index' 的兄弟节点，会得到多个名为 `Index` 的路由互相顶替
--   —— 正是 `src/router/index.js` 注释里记录过的那类事故
--   （当时 `index` 撞名把仪表盘整个顶掉，现象是"总览仪表盘界面不存在"）。
--
--   因此本脚本新增菜单的 path 全部取全仓库唯一值。已占用集合（供后续维护者核对）：
--     index, history, common-param, key-list, public-keys, user-keys, business-users,
--     demo, quick, process, menu, dept, dict, config, notice, post,
--     overview, chain, nodelist, keypool, sessions, distlogs, acceptance, log,
--     keyupdate, keyautoupdate, keydelete, build, gen, swagger, system, tool,
--     operlog, logininfor, role, user
--   本脚本新增：workbench, mylogs, keydist, symkeys, create（均已核对不冲突）。
--
-- 【结构选择】用**顶层 C 类型**（menu_type='C'、parent_id=0、is_frame=1）
--   对顶层 C 类型，后端 `isMenuFrame()` 为真，于是：
--     - 父路由 name 取 EMPTY、path 取 `/`、component 取 Layout；
--     - 子路由 name = capitalize(path)、component = 菜单里的 component。
--   净效果：侧边栏得到**一个**条目，URL 就是 `/<path>`，且路由名唯一。
--   比"顶层目录(M) + 单个子菜单(C)"少一层，URL 也更短。
--   唯一例外见下方 9054（挂到既有 9001「密钥管理」分组下）。
--
--   ⚠️ is_frame 必须写 **1**，不能写 0 —— 这两个值的语义与直觉相反：
--     `UserConstants.YES_FRAME = "0"`（是外链）、`NO_FRAME = "1"`（不是外链）
--     （见 `ruoyi-common/.../constant/UserConstants.java:43,46`，
--      以及 `02.sql:142` 的列注释「是否为外链（0是 1否）」）。
--     `isMenuFrame()` 要求 `isFrame == NO_FRAME`，即 **1**。
--     写成 0 的后果不是"退化成普通菜单"，而是**整站登录后卡死**：
--       isMenuFrame 为假 → component 回落到 LAYOUT → getRouterPath 直接返回 'workbench'
--       （相对路径，没有前导 '/'）。vue-router 4 的 addRoute 对顶层相对 path 会抛
--       "Absolute path must start with /"，该异常又发生在 `permission.js` 的 .catch
--       之外，于是 next() 永远不会被调用 —— 表现为登录成功后一直停在上一个页面。
-- =============================================================================
--
-- 幂等：`INSERT ... ON DUPLICATE KEY UPDATE` + `INSERT ... ON DUPLICATE KEY`，可重复执行。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 工作台 / 我的日志 / 密钥分发 / 对称密钥
--    （顶层 C 类型；url 分别为 /workbench、/mylogs、/keydist、/symkeys）
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9050, '工作台', 0, 5, 'workbench', 'workbench/index', 1, 0,
        'C', '0', '0', '', 'dashboard', 'admin', NOW(),
        '阶段1 自 kms-user 迁入：views/workbench/index.vue（原 WorkbenchView.vue）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        icon = VALUES(icon), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9051, '我的日志', 0, 70, 'mylogs', 'logs/index', 1, 0,
        'C', '0', '0', '', 'log', 'admin', NOW(),
        '阶段1 自 kms-user 迁入：views/logs/index.vue（原 MyLogsView.vue）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        icon = VALUES(icon), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9052, '密钥分发', 0, 25, 'keydist', 'distribute/index', 1, 0,
        'C', '0', '0', '', 'share', 'admin', NOW(),
        '阶段1 自 kms-user 迁入：views/distribute/index.vue（原 DistributeView.vue）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        icon = VALUES(icon), remark = VALUES(remark);

INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES (9053, '对称密钥', 0, 26, 'symkeys', 'distribute/symmetricKeys', 1, 0,
        'C', '0', '0', '', 'lock', 'admin', NOW(),
        '阶段1 自 kms-user 迁入：views/distribute/symmetricKeys.vue（原 SymmetricKeysView.vue）')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), menu_type = VALUES(menu_type),
                        icon = VALUES(icon), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 2. 生成密钥：挂到既有 9001「密钥管理」分组下（URL 为 /key/create）
-- ---------------------------------------------------------------------------
-- 21_remove_key_generate_menu_and_collapse_roles.sql 删掉了旧的 4000「生成密钥」，
-- 但 9001「密钥管理」分组仍在，其下有 5000 密钥更新 / 6000 密钥自动更新 /
-- 7000 密钥回收 / 9011 生成历史 / 9012 公共参数。
-- 把迁入的生成表单补进同一分组，order_num=1（原 4000 腾出的位置），
-- 与文档 §9.3「密钥生成」分组把「密钥生成 / 生成历史 / 密钥查询」并列的意图一致。
--
-- ⚠️ 这一步刻意**不是**顶层 C 类型：生成页与更新/回收同属「密钥」业务，
--    散到顶层会让侧边栏出现两个语义重叠的入口。
--
-- 用子查询取父目录而非硬编码 9001：若上游把「密钥管理」改名/删掉，
-- 本语句会插入 0 行并留痕于下方自检，而不是把菜单挂到一个不存在的父节点上
-- （挂空父节点会让整个分组在侧边栏里消失，属最难排查的一类菜单故障）。
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
SELECT 9054, '生成密钥', p.menu_id, 1, 'create', 'generate/create', 1, 0,
       'C', '0', '0', '', 'form', 'admin', NOW(),
       '阶段1 自 kms-user 迁入：views/generate/create.vue（原 GenerateView.vue）'
FROM (SELECT menu_id FROM sys_menu
      WHERE menu_id = 9001 AND menu_type = 'M' AND status = '0'
      LIMIT 1) p
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        component = VALUES(component), remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 3. 角色映射
-- ---------------------------------------------------------------------------
-- 说明：`admin` 账号走**超管豁免**（RuoYi 里 admin 不看 sys_role_menu），
-- 这里补映射是为了**其他持有 admin 角色的账号**也能看到，与 20/25/26/29 号一致。
--
-- role_id=2（普通角色）**刻意不授权**：
--   - 本仓库中唯一的 role_id=2 账号是 `acceptance_user`（19 号脚本，验收压测专用）；
--   - 阶段 1 已移除 role_level 分流，可见范围完全由菜单决定，
--     非管理员若被授予这些菜单会直接看到管理端页面；
--   - 节点/普通用户的业务视图分流属**阶段 2**（principal_type），本轮不预先发明该字段。
--     待阶段 2 定下 NODE 主体后，再按新模型统一授权。
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9050), (1, 9051), (1, 9052), (1, 9053), (1, 9054)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- ---------------------------------------------------------------------------
-- 4. 自检
-- ---------------------------------------------------------------------------
SELECT '阶段1 迁入菜单' AS check_item, menu_id, menu_name, parent_id, path, component, order_num
FROM sys_menu WHERE menu_id BETWEEN 9050 AND 9054
ORDER BY menu_id;

SELECT '阶段1 角色映射' AS check_item, rm.role_id, r.role_name, rm.menu_id
FROM sys_role_menu rm JOIN sys_role r ON r.role_id = rm.role_id
WHERE rm.menu_id BETWEEN 9050 AND 9054
ORDER BY rm.menu_id;

-- 路由名唯一性：本脚本新增菜单的 capitalize(path) 不得与任何**会生成路由**的菜单重复。
-- 期望结果为空集 —— 有行返回就说明会撞名，必须改名后才可上线。
--
-- ⚠️ 必须只统计 menu_type IN ('M','C')：后端 `buildMenus` 只会把目录(M)与菜单(C)
--    转成路由，按钮权限(F)不参与，因此 F 行即使 path 重复也无害。
--    实测库里有 5 条 path='' 与 13 条 path='#' 的 F 行（RuoYi 初始化数据自带），
--    不过滤就会让本检查**恒返回非空**——一个恒假的告警比没有告警更糟，
--    它会训练读者忽略这块输出。
SELECT '路由名冲突（应为空）' AS check_item, LOWER(m.path) AS colliding_path, COUNT(*) AS cnt
FROM sys_menu m
WHERE m.status = '0' AND m.menu_type IN ('M', 'C')
GROUP BY LOWER(m.path)
HAVING COUNT(*) > 1;

-- 9054（生成密钥）依赖 9001「密钥管理」分组存在。
-- resolved_rows = 0 说明上游菜单结构已变，需按新结构重新挂载（不是报错，是提示）。
SELECT '生成密钥父目录解析' AS check_item, COUNT(*) AS resolved_rows
FROM sys_menu WHERE menu_id = 9054;
