-- 修复统一公共菜单的乱码（历史上 UTF-8 文本被错误按 latin1 再次写入）
UPDATE sys_menu
SET menu_name = CONVERT(BINARY CONVERT(menu_name USING latin1) USING utf8mb4)
WHERE menu_id IN (4, 100, 101, 102, 108, 500, 501);
