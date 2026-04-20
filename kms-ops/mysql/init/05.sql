SET NAMES utf8mb4;
insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('4000', '密钥生成', '0', '2', 'keygenerate', 'keygenerate/index', 1, 0, 'C', '0', '0', 'keyuser:keyuser:list', 'peoples', 'admin', sysdate(), '', null, '用户管理菜单');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('5000', '密钥更新', '0', '3', 'keyupdate', 'keyupdate/index', 1, 0, 'C', '0', '0', 'keymanage:keymanage:edit', 'system', 'admin', sysdate(), '', null, '密钥管理菜单');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('6000', '密钥自动更新', '0', '4', 'keyautoupdate', 'keyautoupdate/index', 1, 0, 'C', '0', '0', 'keymanage:keymanage:edit', 'system', 'admin', sysdate(), '', null, '密钥管理菜单');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('7000', '密钥回收', '0', '5', 'keydelete', 'keydelete/index', 1, 0, 'C', '0', '0', 'keymanage:keymanage:list', 'system', 'admin', sysdate(), '', null, '密钥管理菜单');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('8000', '区块链查看', '0', '7', 'blockchain', 'blockchain/index', 1, 0, 'C', '0', '0', 'keyuser:keyuser:list', 'peoples', 'admin', sysdate(), '', null, '用户管理菜单');


insert into sys_role_menu values ('2', '4000');
insert into sys_role_menu values ('2', '5000');
insert into sys_role_menu values ('2', '6000');
insert into sys_role_menu values ('2', '7000');
insert into sys_role_menu values ('2', '8000');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('2002', '密钥管理新增', '4000', '2',  '#', '', 1, 0, 'F', '0', '0', 'keymanage:keymanage:add',          '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('2003', '密钥管理修改', '5000', '3',  '#', '', 1, 0, 'F', '0', '0', 'keymanage:keymanage:edit',         '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('2004', '密钥管理修改', '6000', '3',  '#', '', 1, 0, 'F', '0', '0', 'keymanage:keymanage:edit',         '#', 'admin', sysdate(), '', null, '');

insert into sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
values('2005', '密钥管理删除', '7000', '4',  '#', '', 1, 0, 'F', '0', '0', 'keymanage:keymanage:remove',       '#', 'admin', sysdate(), '', null, '');


insert into sys_role_menu values ('2', '2002');
insert into sys_role_menu values ('2', '2003');
insert into sys_role_menu values ('2', '2004');
insert into sys_role_menu values ('2', '2005');
