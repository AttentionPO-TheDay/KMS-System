SET NAMES utf8mb4;
-- 统一三大系统共用后台菜单的名称、排序和图标
UPDATE sys_menu SET menu_name = '系统管理', order_num = 80, path = 'system', icon = 'system', visible = '0', status = '0'
WHERE menu_id = 4;

UPDATE sys_menu SET menu_name = '系统工具', order_num = 81, path = 'tool', icon = 'tool', visible = '0', status = '0'
WHERE menu_id = 5;

UPDATE sys_menu SET menu_name = '日志审计', order_num = 82, path = 'log', icon = 'log', visible = '0', status = '0'
WHERE menu_id = 108;

UPDATE sys_menu SET menu_name = '角色管理', parent_id = 4, order_num = 1, path = 'role', component = 'system/role/index', icon = 'peoples', visible = '0', status = '0'
WHERE menu_id = 101;

UPDATE sys_menu SET menu_name = '表单构建', parent_id = 5, order_num = 1, path = 'build', component = 'tool/build/index', icon = 'build', visible = '0', status = '0'
WHERE menu_id = 115;

UPDATE sys_menu SET menu_name = '代码生成', parent_id = 5, order_num = 2, path = 'gen', component = 'tool/gen/index', icon = 'code', visible = '0', status = '0'
WHERE menu_id = 116;

UPDATE sys_menu SET menu_name = '系统接口', parent_id = 5, order_num = 3, path = 'swagger', component = 'tool/swagger/index', icon = 'swagger', visible = '0', status = '0'
WHERE menu_id = 117;

UPDATE sys_menu SET menu_name = '操作日志', parent_id = 108, order_num = 1, path = 'operlog', component = 'monitor/operlog/index', icon = 'form', visible = '0', status = '0'
WHERE menu_id = 500;

UPDATE sys_menu SET menu_name = '登录日志', parent_id = 108, order_num = 2, path = 'logininfor', component = 'monitor/logininfor/index', icon = 'logininfor', visible = '0', status = '0'
WHERE menu_id = 501;
