SET NAMES utf8mb4;
DROP TABLE IF EXISTS `keymanage`;

CREATE TABLE `keymanage` (
    `key_id` INT AUTO_INCREMENT COMMENT '密钥ID',
    `user_id` bigint(20) NOT NULL COMMENT '用户ID',
    `user_name` VARCHAR(255) NOT NULL COMMENT '用户名',

    -- 业务核心字段
    `encryt_type` VARCHAR(255) NOT NULL COMMENT '加密算法类型',
    `encryt_name` VARCHAR(255) NOT NULL COMMENT '加密算法名称',
    `key_name` VARCHAR(255) NOT NULL COMMENT '密钥名称',
    `key_use` VARCHAR(255) NOT NULL COMMENT '密钥用途',
    `key_value` VARCHAR(1024) NOT NULL COMMENT '密钥值',

    -- 时间与状态字段
    `cre_time` VARCHAR(255) NOT NULL COMMENT '创建时间',
    `upd_time` VARCHAR(255) NOT NULL COMMENT '更新时间',
    `auto_update` VARCHAR(255) NOT NULL COMMENT '密钥自动更新状态',
    `status` VARCHAR(255) NOT NULL COMMENT '密钥禁用状态(对应Java枚举: 0=正常, 1=冻结, 2=轮换, 3=回收)',

    -- 区块链存证字段 (新增融合)
    `version` INT DEFAULT 1 COMMENT '密钥版本号',
    `chain_hash` VARCHAR(100) DEFAULT NULL COMMENT '区块链交易Hash',
    `block_height` BIGINT DEFAULT NULL COMMENT '区块高度',
    `chain_status` CHAR(1) DEFAULT '0' COMMENT '上链状态(0=待上链, 1=已上链, 2=失败)',

    -- 预留字段 (需要时解除注释并同步Java实体类)
    `ua` VARCHAR(1024) DEFAULT NULL COMMENT '用户部分公钥',
    `key_domain` VARCHAR(255) DEFAULT NULL COMMENT '密钥域',
    `demo_node_id` VARCHAR(255) DEFAULT NULL COMMENT 'PQKDS示例业务节点ID',
    `demo_record_id` VARCHAR(255) DEFAULT NULL COMMENT 'PQKDS示例生成记录ID',
    `demo_result_status` VARCHAR(64) DEFAULT NULL COMMENT 'PQKDS示例生成结果状态',

    PRIMARY KEY (`key_id`),
    FOREIGN KEY (`user_id`) REFERENCES `sys_user`(`user_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB COMMENT='密钥管理';

-- 全新安装不注入历史示例密钥，业务记录由实际操作产生。
