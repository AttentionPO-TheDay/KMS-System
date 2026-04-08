package com.ruoyi.generate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * kms-generate Java Backend
 * 密钥生成系统 - Spring Boot 启动类
 *
 * 职责：
 * 1. 消费生成消息 (key_generate_log topic)
 * 2. 用户鉴权终校验
 * 3. 生成记录入库
 * 4. 触发上链
 * 5. 提供生成记录查询接口
 * 6. 记录生成审计日志
 *
 * TODO: Agent 4 将实现以下模块：
 * - GenerateKafkaConsumer (ENROLL_KEY 消费)
 * - GenerateKeyService (生成记录服务)
 * - GenerateChainService (上链服务)
 * - GenerateAuditService (审计服务)
 * - GenerateKeyController (查询接口)
 */
@SpringBootApplication
@EnableKafka
@EnableScheduling
public class KmsGenerateApplication {

    public static void main(String[] args) {
        SpringApplication.run(KmsGenerateApplication.class, args);
        System.out.println("=================================================");
        System.out.println("  kms-generate Java Backend Started Successfully  ");
        System.out.println("  Port: 8081 (API), 8082 (Go Backend)            ");
        System.out.println("  Topic: key_generate_log                         ");
        System.out.println("=================================================");
    }
}
