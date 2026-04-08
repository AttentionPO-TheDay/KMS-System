package config

import (
	"os"
)

// Kafka 配置
var (
	KafkaAddr  = getEnv("KAFKA_ADDR", "kafka:9092")
	KafkaTopic = getEnv("KAFKA_TOPIC", "key_generate_log")
)

// Server 配置
var (
	ServerPort = getEnv("SERVER_PORT", "8081")
)

// App 配置
var (
	AppName = "key-service-generate"
)

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}