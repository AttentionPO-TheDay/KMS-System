package com.ruoyi.updatedel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * kms-updatedel Java Backend
 * 密钥更新与回收系统 - Spring Boot 启动类
 *
 * 职责：
 * 1. 消费更新消息 (key_update_log topic)
 * 2. 消费回收消息 (key_revoke_log topic)
 * 3. 执行轮换
 * 4. 执行逻辑回收
 * 5. 写生命周期日志
 * 6. 触发上链
 * 7. 权限审批
 * 8. 自动回退定时任务
 *
 * TODO: Agent 5 将实现以下模块：
 * - UpdateKafkaConsumer (UPDATE_KEY 消费)
 * - RevokeKafkaConsumer (REVOKE_KEY 消费)
 * - LifecycleChainConsumer (上链任务消费)
 * - KeyRotateService (轮换服务)
 * - KeyRevokeService (回收服务)
 * - LifecycleKeyController (生命周期查询接口)
 * - PermissionRequestController (权限申请审批)
 * - PermissionRollbackTaskService (自动回退服务)
 */
@SpringBootApplication
@EnableKafka
@EnableScheduling
public class KmsUpdatedelApplication {

    public static void main(String[] args) {
        SpringApplication.run(KmsUpdatedelApplication.class, args);
        System.out.println("===================================================");
        System.out.println("  kms-updatedel Java Backend Started Successfully ");
        System.out.println("  Topics: key_update_log, key_revoke_log          ");
        System.out.println("  Permission Auto-Rollback: Enabled (30min)      ");
        System.out.println("===================================================");
    }
}
