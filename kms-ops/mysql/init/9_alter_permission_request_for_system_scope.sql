ALTER TABLE permission_request
  ADD COLUMN IF NOT EXISTS system_code VARCHAR(32) NOT NULL DEFAULT 'lifecycle' COMMENT '所属系统编码(generate/lifecycle/distribute)' AFTER user_name,
  ADD COLUMN IF NOT EXISTS feature_code VARCHAR(64) NOT NULL DEFAULT 'AUTO_UPDATE' COMMENT '功能编码' AFTER system_code,
  ADD COLUMN IF NOT EXISTS feature_name VARCHAR(100) DEFAULT NULL COMMENT '功能名称' AFTER feature_code;
