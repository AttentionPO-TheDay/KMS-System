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

    PRIMARY KEY (`key_id`),
    FOREIGN KEY (`user_id`) REFERENCES `sys_user`(`user_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB COMMENT='密钥管理';

-- 插入测试数据 (新字段会自动使用默认值: version=1, chain_status='0')
INSERT INTO `keymanage` (`user_id`, `user_name`, `encryt_type`, `encryt_name`, `key_name`, `key_use`, `key_value`, `cre_time`, `upd_time`, `auto_update`, `status`)
VALUES (1, 'example_user', 'AES', 'AES-256', 'example_key', 'encryption', 's3cr3tK3y', '2023-10-10 12:00:00', '2023-10-10 12:00:00', 'enabled', 3');