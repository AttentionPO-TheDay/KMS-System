package com.ruoyi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * kms-updatedel 启动程序。
 */
@SpringBootApplication(nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class)
@EnableKafka
@EnableScheduling
public class KmsUpdatedelApplication
{
    public static void main(String[] args)
    {
        SpringApplication.run(KmsUpdatedelApplication.class, args);
    }
}
