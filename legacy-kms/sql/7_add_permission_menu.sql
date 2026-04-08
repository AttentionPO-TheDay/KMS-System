-- ===================================================================
-- 添加权限审批菜单到系统菜单表
-- 执行此脚本后，刷新页面即可在侧边栏看到"权限审批"菜单
-- ===================================================================

-- 1. 添加权限审批菜单（一级菜单）
INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
VALUES ('权限审批', 0, 5, 'permission', NULL, 1, 0, 'M', '0', '0', NULL, 'edit', 'admin', NOW(), '', NULL, '权限申请审批管理菜单');

-- 2. 获取刚插入的菜单ID（用于下一步）
SET @parent_menu_id = LAST_INSERT_ID();

-- 3. 添加权限审批列表子菜单
INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
VALUES ('权限申请', @parent_menu_id, 1, 'request', 'permission/request/index', 1, 0, 'C', '0', '0', 'permission:request:list', 'list', 'admin', NOW(), '', NULL, '权限申请审批列表');

-- 4. 获取权限申请菜单ID
SET @request_menu_id = LAST_INSERT_ID();

-- 5. 添加按钮权限
INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
VALUES 
('审批通过', @request_menu_id, 1, '#', '', 1, 0, 'F', '0', '0', 'permission:request:approve', '#', 'admin', NOW(), '', NULL, ''),
('审批拒绝', @request_menu_id, 2, '#', '', 1, 0, 'F', '0', '0', 'permission:request:reject', '#', 'admin', NOW(), '', NULL, ''),
('查看详情', @request_menu_id, 3, '#', '', 1, 0, 'F', '0', '0', 'permission:request:query', '#', 'admin', NOW(), '', NULL, '');

-- 执行成功后，请：
-- 1. 刷新浏览器页面
-- 2. 重新登录（如果刷新后仍看不到）
-- 3. 在左侧菜单栏应该能看到"权限审批"菜单项
