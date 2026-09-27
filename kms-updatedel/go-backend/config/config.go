package config

import (
	"os"
	"strconv"
	"sync"
)

// Config holds all configuration for the lifecycle service.
type Config struct {
	// Server
	ServerPort    string
	InternalToken string

	// Kafka
	KafkaBrokers string
	UpdateTopic  string
	RevokeTopic  string

	// Redis (for idempotency)
	RedisAddr     string
	RedisPassword string
	RedisDB       int

	// Idempotency TTL (seconds)
	IdempotencyTTL int
}

var (
	cfg  *Config
	once sync.Once
)

// Get returns the global config singleton.
func Get() *Config {
	once.Do(func() {
		cfg = &Config{
			ServerPort: getEnv("SERVER_PORT", "8082"),
			// 必须由环境变量 INTERNAL_TOKEN 注入，无默认值：
			// 历史默认值为公开值，泄露后可触达更新/回收/批量回收接口。
			InternalToken:  getEnvRequired("INTERNAL_TOKEN"),
			KafkaBrokers:   getEnv("KAFKA_BROKERS", "localhost:9092"),
			UpdateTopic:    getEnv("KAFKA_UPDATE_TOPIC", "key_update_log"),
			RevokeTopic:    getEnv("KAFKA_REVOKE_TOPIC", "key_revoke_log"),
			RedisAddr:      getEnv("REDIS_ADDR", "localhost:6379"),
			RedisPassword:  getEnv("REDIS_PASSWORD", ""),
			RedisDB:        getEnvInt("REDIS_DB", 0),
			IdempotencyTTL: getEnvInt("IDEMPOTENCY_TTL", 300),
		}
	})
	return cfg
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}

// getEnvRequired 读取必填环境变量；缺失时立即 panic，
// 避免以不安全的公开默认值继续启动。
func getEnvRequired(key string) string {
	v := os.Getenv(key)
	if v == "" {
		panic("必填环境变量缺失: " + key + "。请参照 kms-ops/.env.example 配置后再启动。")
	}
	return v
}

func getEnvInt(key string, defaultVal int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return defaultVal
}
