SELECT user_id, user_name, role_level FROM sys_user WHERE user_name='user_01';
SELECT request_id, user_id, user_name, original_level, request_level, status, rollback_time FROM permission_request WHERE user_id=100 ORDER BY request_time DESC LIMIT 3;
