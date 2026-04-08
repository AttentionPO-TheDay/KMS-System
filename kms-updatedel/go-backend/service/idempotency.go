package service

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"

	"key-service-lifecycle/config"
)

// IdempotencyService provides Redis-based idempotent deduplication for lifecycle requests.
type IdempotencyService struct {
	client *redis.Client
	ttl     time.Duration
	mu      sync.RWMutex
	ctx     context.Context
}

var (
	idempService *IdempotencyService
	idempOnce    sync.Once
)

// GetIdempotencyService returns the singleton IdempotencyService.
func GetIdempotencyService() *IdempotencyService {
	idempOnce.Do(func() {
		cfg := config.Get()
		client := redis.NewClient(&redis.Options{
			Addr:     cfg.RedisAddr,
			Password: cfg.RedisPassword,
			DB:       cfg.RedisDB,
		})

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		if err := client.Ping(ctx).Err(); err != nil {
			// Redis unavailable — log and continue without idempotency
			fmt.Printf("[WARN] Redis unavailable for idempotency: %v. Proceeding without dedup.\n", err)
		} else {
			fmt.Println("[INFO] Redis idempotency service connected")
		}

		idempService = &IdempotencyService{
			client: client,
			ttl:     time.Duration(cfg.IdempotencyTTL) * time.Second,
			ctx:     context.Background(),
		}
	})
	return idempService
}

// CheckAndSet attempts to set a lock key for the given (action, keyId, user) tuple.
// Returns true if this is a new request (lock acquired), false if it's a duplicate.
func (s *IdempotencyService) CheckAndSet(action string, keyId int64, user string) (bool, error) {
	lockKey := s.buildKey(action, keyId, user)

	// Use SetNX for atomic check-and-set
	ok, err := s.client.SetNX(s.ctx, lockKey, "1", s.ttl).Result()
	if err != nil {
		// If Redis fails, allow the request through (fail-open for availability)
		return true, fmt.Errorf("redis error: %w", err)
	}
	return ok, nil
}

func (s *IdempotencyService) buildKey(action string, keyId int64, user string) string {
	return fmt.Sprintf("idemp:lifecycle:%s:%d:%s", action, keyId, user)
}

// Close closes the Redis connection.
func (s *IdempotencyService) Close() error {
	if s.client != nil {
		return s.client.Close()
	}
	return nil
}
