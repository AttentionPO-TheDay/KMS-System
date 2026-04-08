-- ===================================================================
-- 权限申请表创建脚本
-- 用于用户申请临时权限提升
-- 日期: 2025-12-08
-- ===================================================================

CREATE TABLE IF NOT EXISTS permission_request (
  request_id        BIGINT(20)      NOT NULL AUTO_INCREMENT   COMMENT '申请ID',
  user_id           BIGINT(20)      NOT NULL                  COMMENT '申请用户ID',
  user_name         VARCHAR(30)     NOT NULL                  COMMENT '申请用户名',
  original_level    INT             NOT NULL                  COMMENT '原始权限等级',
  request_level     INT             NOT NULL                  COMMENT '申请的权限等级（1中级用户，0管理员）',
  request_reason    VARCHAR(500)    DEFAULT NULL              COMMENT '申请理由',
  status            CHAR(1)         DEFAULT '0'               COMMENT '申请状态（0待审批 1已通过 2已拒绝 3已使用并回退）',
  is_temp           TINYINT(1)      DEFAULT 1                 COMMENT '是否临时权限（1是 0否）',
  request_time      DATETIME        NOT NULL                  COMMENT '申请时间',
  approve_by        VARCHAR(64)     DEFAULT NULL              COMMENT '审批人',
  approve_time      DATETIME        DEFAULT NULL              COMMENT '审批时间',
  approve_note      VARCHAR(500)    DEFAULT NULL              COMMENT '审批备注',
  use_time          DATETIME        DEFAULT NULL              COMMENT '权限使用时间',
  rollback_time     DATETIME        DEFAULT NULL              COMMENT '权限回退时间',
  create_time       DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_time       DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (request_id),
  INDEX idx_user_id (user_id),
  INDEX idx_status (status)
) ENGINE=INNODB AUTO_INCREMENT=1 COMMENT = '权限申请表';
