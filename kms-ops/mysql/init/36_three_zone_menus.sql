-- =============================================================================
-- 36_three_zone_menus.sql
-- -----------------------------------------------------------------------------
-- 阶段 9（文档 §9.3）：菜单重组为「三子系统 + 综合管理」四个分区。
--
-- 目标结构
-- --------
--   密钥生成      ├ 密钥生成 / 生成历史 / 密钥查询
--   密钥更新与回收 ├ 密钥更新 / 自动更新 / 密钥回收
--   密钥分发      ├ 分发总览 / 预分配密钥池 / 会话密钥 / 分发日志 / 区块链存证
--   综合管理      ├ 节点管理 / 节点授权 / 操作日志 / 算法说明 / 验收测试台
--
-- 做法：**复用既有 menu_id，只改 parent_id 与 order_num**。
-- 不新建重复菜单、不改 path/component —— 那会打断书签与前端 loadView 解析。
-- 这样也天然幂等：重复执行只是把同一批行再设成同样的父级。
--
-- ⚠️ 只挂**页面确实存在**的菜单
-- ---------------------------------
-- 文档 §9.3 还列了「版本历史」「一致性检查」「异常/泄漏分析」三项。
-- 本脚本**不**为它们建菜单 —— 对应前端页面尚不存在，挂了会点出 404，
-- 比没有菜单更糟（用户会以为页面坏了）。待页面补齐后再单独加。
-- 这是如实反映实现进度，不是遗漏。
--
-- ⚠️ 系统管理只隐藏，不删除（文档阶段 9 第 2 项）
-- ------------------------------------------------
-- 通用 RuoYi 的「系统管理」整组设 visible='1'（隐藏）。
-- **sys_menu 表本身绝不能删** —— 侧边栏完全由它驱动。
--
-- 幂等：全部为 UPDATE / INSERT ... ON DUPLICATE KEY UPDATE。
-- =============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 四个顶层分区（沿用 9xxx 段；菜单表已占用的区间见 30_*.sql 的说明）
-- ---------------------------------------------------------------------------
INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache,
                      menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES
 (9400, '密钥生成',       0, 10, 'genzone',  NULL, 1, 0, 'M', '0', '0', '', 'form',      'admin', NOW(), '阶段9 三子系统分区一：负责出生'),
 (9410, '密钥更新与回收', 0, 20, 'lifezone', NULL, 1, 0, 'M', '0', '0', '', 'refresh',   'admin', NOW(), '阶段9 三子系统分区二：存续、轮换与终止'),
 (9420, '密钥分发',       0, 30, 'distzone', NULL, 1, 0, 'M', '0', '0', '', 'share',     'admin', NOW(), '阶段9 三子系统分区三：使用，并建立短期会话'),
 (9430, '综合管理',       0, 90, 'govzone',  NULL, 1, 0, 'M', '0', '0', '', 'setting',   'admin', NOW(), '阶段9 治理与支撑：节点、审计、算法说明、验收')
ON DUPLICATE KEY UPDATE menu_name = VALUES(menu_name), parent_id = VALUES(parent_id),
                        order_num = VALUES(order_num), path = VALUES(path),
                        menu_type = VALUES(menu_type), icon = VALUES(icon),
                        remark = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 2. 分区一：密钥生成
-- ---------------------------------------------------------------------------
-- 9054 = 生成密钥（阶段1 迁入的用户前台生成页）
UPDATE sys_menu SET parent_id = 9400, order_num = 1 WHERE menu_id = 9054;
-- 9011 = 生成历史
UPDATE sys_menu SET parent_id = 9400, order_num = 2 WHERE menu_id = 9011;
-- 9021 = 用户密钥查询（原在 9002「密钥查询」目录下）
UPDATE sys_menu SET parent_id = 9400, order_num = 3 WHERE menu_id = 9021;

-- ---------------------------------------------------------------------------
-- 3. 分区二：密钥更新与回收
-- ---------------------------------------------------------------------------
UPDATE sys_menu SET parent_id = 9410, order_num = 1 WHERE menu_id = 5000;  -- 密钥更新
UPDATE sys_menu SET parent_id = 9410, order_num = 2 WHERE menu_id = 6000;  -- 密钥自动更新
UPDATE sys_menu SET parent_id = 9410, order_num = 3 WHERE menu_id = 7000;  -- 密钥回收

-- ---------------------------------------------------------------------------
-- 4. 分区三：密钥分发
-- ---------------------------------------------------------------------------
UPDATE sys_menu SET parent_id = 9420, order_num = 1 WHERE menu_id = 9101;  -- 分发总览
UPDATE sys_menu SET parent_id = 9420, order_num = 2 WHERE menu_id = 9104;  -- 预分配密钥池
UPDATE sys_menu SET parent_id = 9420, order_num = 3 WHERE menu_id = 9105;  -- 会话密钥
UPDATE sys_menu SET parent_id = 9420, order_num = 4 WHERE menu_id = 9106;  -- 分发日志
UPDATE sys_menu SET parent_id = 9420, order_num = 5 WHERE menu_id = 9102;  -- 区块链存证
-- 9052/9053 是阶段1 迁入的「密钥分发」「对称密钥」页。
-- 与 9101（分发总览）语义重叠，但**页面不同**（前者是用户侧发起分发、
-- 后者是管理视角的总览），都保留，排在后面。
UPDATE sys_menu SET parent_id = 9420, order_num = 6 WHERE menu_id = 9052;  -- 密钥分发（发起）
UPDATE sys_menu SET parent_id = 9420, order_num = 7 WHERE menu_id = 9053;  -- 对称密钥

-- ---------------------------------------------------------------------------
-- 5. 分区四：综合管理
-- ---------------------------------------------------------------------------
UPDATE sys_menu SET parent_id = 9430, order_num = 1 WHERE menu_id = 9103;  -- 节点管理
UPDATE sys_menu SET parent_id = 9430, order_num = 2 WHERE menu_id = 9005;  -- 节点授权（目录）
UPDATE sys_menu SET parent_id = 9430, order_num = 3 WHERE menu_id = 108;   -- 操作日志
UPDATE sys_menu SET parent_id = 9430, order_num = 4 WHERE menu_id = 9031;  -- 算法图解与演示
UPDATE sys_menu SET parent_id = 9430, order_num = 5 WHERE menu_id = 9201;  -- 验收测试台

-- 9051「我的日志」也是日志，但它是**节点自己的**流水（区别于管理视角的
-- 操作日志 108），归入综合管理更自然。
UPDATE sys_menu SET parent_id = 9430, order_num = 6 WHERE menu_id = 9051;

-- 9050「工作台」保持顶层单页（它是入口而非分区成员），不动。

-- ---------------------------------------------------------------------------
-- 6. 隐藏通用系统管理（只隐藏，不删除）
-- ---------------------------------------------------------------------------
-- 文档阶段 9 第 2 项。系统管理下的用户/角色/菜单/部门/岗位/字典/参数/通知
-- 都是 RuoYi 自带的通用功能，本系统不使用；但**行必须留着** ——
-- 删了菜单表，侧边栏整个就没了。
UPDATE sys_menu SET visible = '1' WHERE menu_id = 4;

-- ---------------------------------------------------------------------------
-- 6.5 剩余成员的归属（自检发现旧目录里还留着这些，逐个归位）
-- ---------------------------------------------------------------------------
-- 公共参数：文档 §9.3 说「纯技术页面如仍有必要，可作为算法说明/高级设置中的
-- 二级页面，不再占据三个主子系统的核心菜单」。归入综合管理，与算法说明并列。
UPDATE sys_menu SET parent_id = 9430, order_num = 7 WHERE menu_id = 9012;  -- 公共参数

-- 密钥查询的其余三页归入「密钥生成」分区（文档 §9.3 的密钥查询就在该分区下，
-- 与已迁入的 9021 用户密钥查询并列）。
UPDATE sys_menu SET parent_id = 9400, order_num = 4 WHERE menu_id = 9022;  -- 公钥查询
UPDATE sys_menu SET parent_id = 9400, order_num = 5 WHERE menu_id = 9023;  -- 用户密钥池
UPDATE sys_menu SET parent_id = 9400, order_num = 6 WHERE menu_id = 9024;  -- 密钥用户管理

-- 算法说明的其余两页归入综合管理，与 9031 并列
UPDATE sys_menu SET parent_id = 9430, order_num = 8 WHERE menu_id = 9032;  -- 更新回收速览
UPDATE sys_menu SET parent_id = 9430, order_num = 9 WHERE menu_id = 9033;  -- 轮换计算揭秘

-- ---------------------------------------------------------------------------
-- 7. 隐藏已清空的旧顶层目录
-- ---------------------------------------------------------------------------
-- 成员全部迁走后，这些旧目录会变成"点开没内容"的空分组 ——
-- 比没有这个分组更让人困惑（会以为菜单没加载出来）。
--
-- ⚠️ 隐藏列表必须覆盖**所有**旧目录，包括 9200「测试」（它的唯一成员 9201
--    已迁入综合管理）。漏掉一个就会在侧边栏留一个空壳。
--    判据仍是结构性的 NOT EXISTS，不是硬编码"哪个空了"。
--
-- ⚠️ 子查询必须**再包一层派生表**，否则 MySQL 报
--    ERROR 1093: You can't specify target table 'p' for update in FROM clause
--    —— 它不允许"更新某表的同时从同一张表里 SELECT"。
--    包一层 `(SELECT ...) AS c` 会让 MySQL 先物化快照，绕开这个限制。
UPDATE sys_menu p SET p.visible = '1'
WHERE p.menu_type = 'M' AND p.visible = '0'
  AND p.menu_id IN (9001, 9002, 9003, 9004, 9005, 9100, 9200)
  AND NOT EXISTS (
      SELECT 1 FROM (
          SELECT parent_id FROM sys_menu
          WHERE visible = '0' AND status = '0'
      ) AS c
      WHERE c.parent_id = p.menu_id
  );

-- ---------------------------------------------------------------------------
-- 8. 角色映射：新分区授权给管理员
-- ---------------------------------------------------------------------------
INSERT INTO sys_role_menu (role_id, menu_id)
VALUES (1, 9400), (1, 9410), (1, 9420), (1, 9430)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- ---------------------------------------------------------------------------
-- 9. 自检
-- ---------------------------------------------------------------------------
SELECT '四个分区' AS check_item, menu_id, menu_name, order_num, visible
FROM sys_menu WHERE menu_id IN (9400, 9410, 9420, 9430) ORDER BY order_num;

SELECT '分区归属' AS check_item, p.menu_name AS zone, c.menu_id, c.menu_name, c.order_num
FROM sys_menu c JOIN sys_menu p ON p.menu_id = c.parent_id
WHERE c.parent_id IN (9400, 9410, 9420, 9430)
ORDER BY p.order_num, c.order_num;

SELECT '仍可见的旧顶层目录（应只剩工作台与四个分区）' AS check_item, menu_id, menu_name, path
FROM sys_menu WHERE parent_id = 0 AND menu_type = 'M' AND visible = '0' ORDER BY order_num;

SELECT '系统管理已隐藏（visible 应为 1）' AS check_item, menu_id, menu_name, visible
FROM sys_menu WHERE menu_id = 4;