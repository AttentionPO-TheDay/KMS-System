package com.ruoyi.updatedel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 密钥更新与回收系统启动类。
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
