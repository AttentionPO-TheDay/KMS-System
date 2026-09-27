-- 把 4 个内嵌菜单的 **component 与 query** 都恢复成正确形式。
-- 用文件而不是命令行 -e，是因为 JSON 里的双引号在 PowerShell → docker exec 的多层
-- 转义里极易被吃掉，结果要么写不进去、要么写进去一个坏值 —— 而 mysql 客户端
-- 在参数被吃错时只会打印一大段 --help，看起来像"执行了"，实际什么都没做。
--
-- 两个字段都要写：只恢复 query 而漏掉 component，会让"component 被改坏"这类
-- 故障在跑完这个脚本后依然存在（我就这么漏过一次，于是以为脚本没生效）。
UPDATE sys_menu SET component = 'frame/index', query = '{"url":"/distribute/"}'            WHERE menu_id = 9101;
UPDATE sys_menu SET component = 'frame/index', query = '{"url":"/distribute/#/blockchain"}' WHERE menu_id = 9102;
UPDATE sys_menu SET component = 'frame/index', query = '{"url":"/distribute/#/node"}'       WHERE menu_id = 9103;
UPDATE sys_menu SET component = 'frame/index', query = '{"url":"/acceptance/"}'             WHERE menu_id = 9201;

SELECT menu_id, path, component, query FROM sys_menu WHERE menu_id IN (9101, 9102, 9103, 9201) ORDER BY menu_id;
