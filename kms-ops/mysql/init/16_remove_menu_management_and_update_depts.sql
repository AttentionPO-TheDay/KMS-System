-- 移除统一后台中的菜单管理，并按最新要求调整公司/部门初始化数据

DELETE FROM sys_role_menu
WHERE menu_id IN (102, 1012, 1013, 1014, 1015);

DELETE FROM sys_menu
WHERE menu_id IN (102, 1012, 1013, 1014, 1015);

UPDATE sys_dept
SET dept_name = CONVERT(0x54455354E585ACE58FB8 USING utf8mb4)
WHERE dept_id = 100;

UPDATE sys_dept
SET dept_name = CONVERT(0xE680BBE585ACE58FB8 USING utf8mb4)
WHERE dept_id = 101;

DELETE FROM sys_dept
WHERE dept_id IN (108, 109, 102);
