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
	ttl    time.Duration
	mu     sync.RWMutex
	ctx    context.Context
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
			fmt.Printf("[ERROR] Redis unavailable for idempotency: %v. Requests requiring dedup will be rejected.\n", err)
		} else {
			fmt.Println("[INFO] Redis idempotency service connected")
		}

		idempService = &IdempotencyService{
			client: client,
			ttl:    time.Duration(cfg.IdempotencyTTL) * time.Second,
			ctx:    context.Background(),
		}
	})
	return idempService
}

// CheckAndSet attempts to set a lock key for the given (action, keyId, user) tuple.
// Returns true if this is a new request (lock acquired), false if it's a duplicate.
func (s *IdempotencyService) CheckAndSet(action string, keyId int64, user string) (bool, error) {
	return s.CheckAndSetWithKey(s.buildKey(action, keyId, user))
}

func (s *IdempotencyService) CheckAndSetWithKey(idempotencyKey string) (bool, error) {
	lockKey := idempotencyKey
	if len(lockKey) < len("idemp:lifecycle:") || lockKey[:len("idemp:lifecycle:")] != "idemp:lifecycle:" {
		lockKey = "idemp:lifecycle:" + idempotencyKey
	}

	// Use SetNX for atomic check-and-set
	ok, err := s.client.SetNX(s.ctx, lockKey, "1", s.ttl).Result()
	if err != nil {
		return false, fmt.Errorf("redis error: %w", err)
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
