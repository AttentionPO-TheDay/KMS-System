-- =====================================================
-- 添加演示专用用户 test (用于计算过程可视化展示)
-- 密码: admin123 (与管理员相同的BCrypt哈希)
-- 角色: 超级管理员 (role_id=1), 确保有全部权限完成演示
-- =====================================================

-- 插入 test 用户 (user_id=3, 部门=研发部门103)
INSERT INTO sys_user (user_id, dept_id, user_name, nick_name, user_type, email, phonenumber, sex, avatar, password, status, del_flag, login_ip, login_date, create_by, create_time, update_by, update_time, remark, role_level)
VALUES (3, 103, 'test', '演示用户', '00', 'test@kms.local', '13800000000', '0', '', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', '127.0.0.1', sysdate(), 'admin', sysdate(), '', null, '专用演示账户-计算过程可视化', 0)
ON DUPLICATE KEY UPDATE user_name = VALUES(user_name);

-- 关联超级管理员角色
INSERT INTO sys_user_role (user_id, role_id) VALUES (3, 1)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

-- 关联岗位
INSERT INTO sys_user_post (user_id, post_id) VALUES (3, 1)
ON DUPLICATE KEY UPDATE post_id = VALUES(post_id);
