-- 删除旧 verify-update-vs-autoupdate.mjs 遗留的验收夹具。
-- 该脚本当时把业务 DELETE（语义为回收）误当成物理清理，导致管理端长期显示
-- acceptance_user 的一条回收记录。条件刻意收紧，避免删除真实业务密钥。
SET NAMES utf8mb4;

SET @obsolete_key_id := (
  SELECT key_id
  FROM kms.keymanage
  WHERE key_id = 4
    AND user_id = 4
    AND user_name = 'acceptance_user'
    AND key_name LIKE '改名4-%'
    AND key_use = '验证用'
    AND status = '3'
  LIMIT 1
);

SET @obsolete_scan_run := (
  SELECT run_id
  FROM kms.key_health_scan_item
  WHERE key_id = @obsolete_key_id
    AND user_name = 'acceptance_user'
  LIMIT 1
);

DELETE FROM kms.key_health_scan_item
WHERE key_id = @obsolete_key_id AND user_name = 'acceptance_user';

DELETE FROM kms.key_health_scan_run
WHERE run_id = @obsolete_scan_run
  AND NOT EXISTS (
    SELECT 1 FROM kms.key_health_scan_item item
    WHERE item.run_id = @obsolete_scan_run
  );

DELETE FROM kms.key_operation_record
WHERE key_id = @obsolete_key_id AND user_name = 'acceptance_user';

DELETE FROM kms.keymanage_version_history
WHERE key_id = @obsolete_key_id;

DELETE FROM kms.keymanage
WHERE key_id = @obsolete_key_id
  AND user_name = 'acceptance_user';
