-- 检查 sys_user 表结构
DESCRIBE sys_user;

-- 检查是否已经有 role_level 字段
SELECT COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = 'ry_vue' 
  AND TABLE_NAME = 'sys_user' 
  AND COLUMN_NAME IN ('role_right_root', 'role_level');
