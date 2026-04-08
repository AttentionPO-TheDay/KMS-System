package com.ruoyi.distribute;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

/**
 * 密钥分发系统启动类
 */
@SpringBootApplication
@EnableFeignClients
public class KmsDistributeApplication {

    public static void main(String[] args) {
        SpringApplication.run(KmsDistributeApplication.class, args);
        System.out.println("========== 密钥分发系统启动成功 ==========");
    }
}
