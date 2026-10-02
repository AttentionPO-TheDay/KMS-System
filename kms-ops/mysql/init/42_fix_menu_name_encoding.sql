-- =============================================================================
-- 42_fix_menu_name_encoding.sql
-- -----------------------------------------------------------------------------
-- 修复 19 个菜单名的**双重编码**（2026-09-30）。
--
-- 与 37_*.sql 是同一类问题、不同的受害文件
-- -----------------------------------------
-- 37_*.sql 修的是 `30_port_user_pages_into_console.sql` 写坏的 5 个菜单名
-- （9050-9054），并指出根因：**该文件漏写 `SET NAMES utf8mb4`**。
--
-- 本次全库扫描发现同一根因还波及另外 10 个文件，其中 20_/25_/26_ 写入了
-- 19 个仍然存活且名字是坏的菜单行：
--
--   9001 密钥管理      9002 密钥查询      9003 算法说明      9004 权限与审计
--   9011 生成历史      9012 公共参数      9022 公钥查询      9024 密钥用户管理
--   9031 算法图解与演示 9032 更新回收速览   9033 轮换计算揭秘
--   9041 菜单管理      9042 部门管理      9043 字典管理      9044 参数设置
--   9045 通知公告      9046 岗位管理      9100 分发与区块链   9200 测试
--
-- 其中 **9011「生成历史」** 被授权给了 role_id=2（节点端「密钥生成」分区），
-- 所以节点登录后侧边栏里那一项显示成 `ç”ŸæˆåŽ†å²` —— 用户可见的故障在这里。
-- 其余 18 个当前 `visible='1'`（隐藏），但 `sys_menu` 是侧边栏的唯一来源，
-- 一旦哪天重新启用就会立刻显形，所以一并修掉，而不是只修看得见的那一个。
--
-- 为什么这些名字坏掉了
-- --------------------
-- 这 10 个文件都含中文却**都没有** `SET NAMES utf8mb4`：
--   20 21 22 23 24 25 26 27 28 29
-- 管道导入（`docker-entrypoint-initdb.d` 或 `docker exec -i … mysql < file`）时，
-- 客户端按默认字符集解析中文 → 再以 utf8mb4 存储 → 双重编码。
--
-- **源头已同时修复**：本次给上述 10 个文件都补上了 `SET NAMES utf8mb4;`
-- （与 31-36、37、41 的既有写法一致）。所以全新初始化不会再产生坏名字；
-- 本脚本只负责修**存量数据**。
-- 判据可复核：36_/41_（有 SET NAMES）写入的菜单名一直是正确的，
-- 20_/25_/26_（没有）写入的是坏的 —— 同一环境同一执行路径，差别就在这一行。
--
-- 修法
-- ----
-- 按 menu_id **直接重写**正确中文，名字取自 20_/26_ 里的原始定义（那两个文件
-- 本身是正常 UTF-8，只是导入时被客户端解码错了）。改一处要同步改另一处。
--
-- ⚠️ 刻意**不**做"反转双重编码"（`CONVERT(BINARY CONVERT(name USING latin1) USING utf8mb4)`）：
--    实测这些坏串是 **cp1252** 而非纯 latin-1（'†' '’' 这类字符根本不在
--    latin-1 里），逆变换会失败或再次写错。这 19 个名字是已知常量，
--    直接写死最稳、可读、可复核 —— 与 37_*.sql 的选择一致。
--
-- 幂等：UPDATE … WHERE menu_id = ?，可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

UPDATE sys_menu SET menu_name = '密钥管理'         WHERE menu_id = 9001;
UPDATE sys_menu SET menu_name = '密钥查询'         WHERE menu_id = 9002;
UPDATE sys_menu SET menu_name = '算法说明'         WHERE menu_id = 9003;
UPDATE sys_menu SET menu_name = '权限与审计'       WHERE menu_id = 9004;
UPDATE sys_menu SET menu_name = '生成历史'         WHERE menu_id = 9011;
UPDATE sys_menu SET menu_name = '公共参数'         WHERE menu_id = 9012;
UPDATE sys_menu SET menu_name = '公钥查询'         WHERE menu_id = 9022;
UPDATE sys_menu SET menu_name = '密钥用户管理'     WHERE menu_id = 9024;
UPDATE sys_menu SET menu_name = '算法图解与演示'   WHERE menu_id = 9031;
UPDATE sys_menu SET menu_name = '更新回收速览'     WHERE menu_id = 9032;
UPDATE sys_menu SET menu_name = '轮换计算揭秘'     WHERE menu_id = 9033;
UPDATE sys_menu SET menu_name = '菜单管理'         WHERE menu_id = 9041;
UPDATE sys_menu SET menu_name = '部门管理'         WHERE menu_id = 9042;
UPDATE sys_menu SET menu_name = '字典管理'         WHERE menu_id = 9043;
UPDATE sys_menu SET menu_name = '参数设置'         WHERE menu_id = 9044;
UPDATE sys_menu SET menu_name = '通知公告'         WHERE menu_id = 9045;
UPDATE sys_menu SET menu_name = '岗位管理'         WHERE menu_id = 9046;
UPDATE sys_menu SET menu_name = '分发与区块链'     WHERE menu_id = 9100;
UPDATE sys_menu SET menu_name = '测试'             WHERE menu_id = 9200;

-- ---------------------------------------------------------------------------
-- 自检
-- ---------------------------------------------------------------------------
SELECT '修复后的菜单名' AS check_item, menu_id, menu_name
FROM sys_menu WHERE menu_id IN (9001,9002,9003,9004,9011,9012,9022,9024,9031,9032,9033,
                                9041,9042,9043,9044,9045,9046,9100,9200)
ORDER BY menu_id;

-- 全表扫描：不应再有双重编码。期望为空集。
-- 判据与 37_*.sql 相同：正常中文的 UTF-8 首字节在 E4..E9，
-- 被二次编码的会落在 C3xx（Ã 开头）。
SELECT '仍存在双重编码（应为空）' AS check_item, menu_id, menu_name
FROM sys_menu
WHERE HEX(LEFT(menu_name, 1)) IN ('C3A5','C3A6','C3A7','C3A8','C3A9','C3B0','C3B1','C3B2');

-- 节点端实际会渲染的那一项，单独回显一次（这是用户可见的判据）
SELECT '节点端「生成历史」' AS check_item, menu_id, menu_name, visible
FROM sys_menu WHERE menu_id = 9011;
