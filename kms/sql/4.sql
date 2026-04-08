-- 菜单 SQL
insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('3000', '用户管理', '0', '1', 'keyuser', 'keyuser/keyuser/index', 1, 0, 'C', '0', '0', 'keyuser:keyuser:list', 'peoples', 'admin', sysdate(), '', null, '用户管理菜单');

-- 按钮父菜单ID
SELECT @parentId := LAST_INSERT_ID();

-- 按钮 SQL
insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('3001', '用户管理查询', @parentId, '1',  '#', '', 1, 0, 'F', '0', '0', 'keyuser:keyuser:query',        '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('3002', '用户管理新增', @parentId, '2',  '#', '', 1, 0, 'F', '0', '0', 'keyuser:keyuser:add',          '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('3003', '用户管理修改', @parentId, '3',  '#', '', 1, 0, 'F', '0', '0', 'keyuser:keyuser:edit',         '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('3004', '用户管理删除', @parentId, '4',  '#', '', 1, 0, 'F', '0', '0', 'keyuser:keyuser:remove',       '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('3005', '用户管理导出', @parentId, '5',  '#', '', 1, 0, 'F', '0', '0', 'keyuser:keyuser:export',       '#', 'admin', sysdate(), '', null, '');


insert into sys_role_menu values ('2', '3000');
insert into sys_role_menu values ('2', '3001');
insert into sys_role_menu values ('2', '3002');
insert into sys_role_menu values ('2', '3003');
insert into sys_role_menu values ('2', '3004');
insert into sys_role_menu values ('2', '3005');