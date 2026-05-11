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
	ServerPort      = getEnv("SERVER_PORT", "8081")
	JavaBackendBase = getEnv("JAVA_BACKEND_BASE", "http://localhost:9081")
	DemoBackendBase = getEnv("DEMO_BACKEND_BASE", "http://localhost:8000/api/pqkds")
)

// 内部鉴权配置
// Java 后端调用 Go 时需在 Header 携带：X-Internal-Token: <InternalToken>
// 只要 Token 匹配，Go 便信任该请求已由 Java 完成鉴权，无需再校验用户密码
var (
	InternalToken = getEnv("INTERNAL_TOKEN", "kms-generate-internal-secret-2026")
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
