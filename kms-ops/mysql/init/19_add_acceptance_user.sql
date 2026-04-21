SET NAMES utf8mb4;
-- =====================================================
-- 添加验收压测专用用户 acceptance_user
-- 密码: admin123 (与现有测试账户一致的 BCrypt 哈希)
-- 角色: 普通用户 (role_id=2), 便于按真实用户口径执行验收压测
-- =====================================================

INSERT INTO sys_user (
  user_id, dept_id, user_name, nick_name, user_type, email, phonenumber, sex, avatar,
  password, status, del_flag, login_ip, login_date, create_by, create_time, update_by,
  update_time, remark, role_level
)
VALUES (
  4, 105, 'acceptance_user', '验收压测用户', '00', 'acceptance@kms.local', '13900000000', '0', '',
  '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', '127.0.0.1', sysdate(), 'admin', sysdate(), '',
  NULL, '测试系统四项压测专用账户', 2
)
ON DUPLICATE KEY UPDATE
  nick_name = VALUES(nick_name),
  email = VALUES(email),
  phonenumber = VALUES(phonenumber),
  password = VALUES(password),
  status = VALUES(status),
  del_flag = VALUES(del_flag),
  remark = VALUES(remark),
  role_level = VALUES(role_level);

INSERT INTO sys_user_role (user_id, role_id)
VALUES (4, 2)
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

INSERT INTO sys_user_post (user_id, post_id)
VALUES (4, 2)
ON DUPLICATE KEY UPDATE post_id = VALUES(post_id);
