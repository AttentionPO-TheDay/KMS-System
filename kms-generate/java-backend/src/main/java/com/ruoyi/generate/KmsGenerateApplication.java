package com.ruoyi.generate;

import org.mybatis.spring.annotation.MapperScan;
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
 */
@SpringBootApplication(scanBasePackages = {"com.ruoyi.generate"})
@EnableKafka
@EnableScheduling
@MapperScan("com.ruoyi.generate.mapper")
public class KmsGenerateApplication {

    public static void main(String[] args) {
        SpringApplication.run(KmsGenerateApplication.class, args);
        System.out.println("=================================================");
        System.out.println("  kms-generate Java Backend Started Successfully  ");
        System.out.println("  Port: 8081                                  ");
        System.out.println("  Topic: key_generate_log (consume)           ");
        System.out.println("  Topic: key_chain_task (consume)             ");
        System.out.println("=================================================");
    }
}
