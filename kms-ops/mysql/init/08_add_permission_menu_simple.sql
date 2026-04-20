SET NAMES utf8mb4;
-- Add permission approval menu
INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES ('Permission Approval', 0, 5, 'permission', NULL, 1, 0, 'M', '0', '0', NULL, 'edit', 'admin', NOW(), 'Permission approval menu');

SET @parent_menu_id = LAST_INSERT_ID();

INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES ('Permission Request', @parent_menu_id, 1, 'request', 'permission/request/index', 1, 0, 'C', '0', '0', 'permission:request:list', 'list', 'admin', NOW(), 'Permission request list');

SET @request_menu_id = LAST_INSERT_ID();

INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
VALUES 
('Approve', @request_menu_id, 1, '#', '', 1, 0, 'F', '0', '0', 'permission:request:approve', '#', 'admin', NOW(), ''),
('Reject', @request_menu_id, 2, '#', '', 1, 0, 'F', '0', '0', 'permission:request:reject', '#', 'admin', NOW(), '');
