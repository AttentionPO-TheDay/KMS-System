package config

import (
	"os"
	"strconv"
	"sync"
)

// Config holds all configuration for the lifecycle service.
type Config struct {
	// Server
	ServerPort string

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
			ServerPort:     getEnv("SERVER_PORT", "8082"),
			KafkaBrokers:   getEnv("KAFKA_BROKERS", "localhost:9092"),
			UpdateTopic:     getEnv("KAFKA_UPDATE_TOPIC", "key_update_log"),
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

func getEnvInt(key string, defaultVal int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return defaultVal
}
