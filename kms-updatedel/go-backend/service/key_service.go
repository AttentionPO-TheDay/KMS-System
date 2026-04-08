package service

import (
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"key-service-lifecycle/config"
	"key-service-lifecycle/models"
	"key-service-lifecycle/utils"
)

const (
	ActionUpdateKey = "UPDATE_KEY"
	ActionRevokeKey = "REVOKE_KEY"
)

// Metrics holds counters for monitoring.
type Metrics struct {
	UpdateRequests    uint64
	UpdateSuccess      uint64
	UpdateQueueFull    uint64
	UpdateErrors       uint64
	RevokeRequests    uint64
	RevokeSuccess     uint64
	RevokeQueueFull   uint64
	RevokeErrors      uint64
	DuplicateRequests uint64
}

var globalMetrics Metrics

// KeyLifecycleService handles UPDATE_KEY and REVOKE_KEY operations.
type KeyLifecycleService struct {
	kafkaProducer *utils.KafkaProducer
	updateChan     chan *models.KeyLifecyclePayload
	revokeChan     chan *models.KeyLifecyclePayload
	workerCount    int
	stopCh         chan struct{}
}

var (
	kms *KeyLifecycleService
	kmsOnce sync.Once
)

// NewKeyLifecycleService creates the singleton service with buffered channels.
func NewKeyLifecycleService() *KeyLifecycleService {
	kmsOnce.Do(func() {
		cfg := config.Get()
		kp := utils.NewKafkaProducer(cfg.KafkaBrokers, cfg.UpdateTopic, cfg.RevokeTopic)

		s := &KeyLifecycleService{
			kafkaProducer: kp,
			updateChan:    make(chan *models.KeyLifecyclePayload, 100000),
			revokeChan:    make(chan *models.KeyLifecyclePayload, 100000),
			workerCount:   10,
			stopCh:        make(chan struct{}),
		}

		for i := 0; i < s.workerCount; i++ {
			go s.updateWorker()
			go s.revokeWorker()
		}

		kms = s
	})
	return kms
}

func (s *KeyLifecycleService) updateWorker() {
	for {
		select {
		case <-s.stopCh:
			return
		case payload := <-s.updateChan:
			s.kafkaProducer.SendUpdate(payload.KeyID, payload)
		}
	}
}

func (s *KeyLifecycleService) revokeWorker() {
	for {
		select {
		case <-s.stopCh:
			return
		case payload := <-s.revokeChan:
			s.kafkaProducer.SendRevoke(payload.KeyID, payload)
		}
	}
}

// EnqueueUpdate adds an UPDATE_KEY payload to the channel. Returns error if full.
func (s *KeyLifecycleService) EnqueueUpdate(payload *models.KeyLifecyclePayload) error {
	atomic.AddUint64(&globalMetrics.UpdateRequests, 1)
	select {
	case s.updateChan <- payload:
		atomic.AddUint64(&globalMetrics.UpdateSuccess, 1)
		return nil
	default:
		atomic.AddUint64(&globalMetrics.UpdateQueueFull, 1)
		return errors.New("update channel full")
	}
}

// EnqueueRevoke adds a REVOKE_KEY payload to the channel. Returns error if full.
func (s *KeyLifecycleService) EnqueueRevoke(payload *models.KeyLifecyclePayload) error {
	atomic.AddUint64(&globalMetrics.RevokeRequests, 1)
	select {
	case s.revokeChan <- payload:
		atomic.AddUint64(&globalMetrics.RevokeSuccess, 1)
		return nil
	default:
		atomic.AddUint64(&globalMetrics.RevokeQueueFull, 1)
		return errors.New("revoke channel full")
	}
}

// GetMetrics returns a copy of the current metrics.
func GetMetrics() Models {
	return Models{
		UpdateRequests:    atomic.LoadUint64(&globalMetrics.UpdateRequests),
		UpdateSuccess:      atomic.LoadUint64(&globalMetrics.UpdateSuccess),
		UpdateQueueFull:    atomic.LoadUint64(&globalMetrics.UpdateQueueFull),
		UpdateErrors:       atomic.LoadUint64(&globalMetrics.UpdateErrors),
		RevokeRequests:    atomic.LoadUint64(&globalMetrics.RevokeRequests),
		RevokeSuccess:     atomic.LoadUint64(&globalMetrics.RevokeSuccess),
		RevokeQueueFull:   atomic.LoadUint64(&globalMetrics.RevokeQueueFull),
		RevokeErrors:      atomic.LoadUint64(&globalMetrics.RevokeErrors),
		DuplicateRequests: atomic.LoadUint64(&globalMetrics.DuplicateRequests),
	}
}

// Models is the exported metrics type (capital M to avoid conflict with models package).
type Models Metrics

// Close shuts down the service and its workers.
func (s *KeyLifecycleService) Close() {
	close(s.stopCh)
	if s.kafkaProducer != nil {
		s.kafkaProducer.Close()
	}
}

// NewKeyLifecyclePayload constructs a payload with traceId and timestamps.
func NewKeyLifecyclePayload(traceId, action, user, password string, keyId int64, km *models.Keymanage) *models.KeyLifecyclePayload {
	now := time.Now().Format("2006-01-02 15:04:05")
	return &models.KeyLifecyclePayload{
		TraceID:     traceId,
		ActionType:  action,
		RawUser:     user,
		RawPassword: password,
		KeyID:       keyId,
		KeyInfo: models.Keymanage{
			KeyID:    keyId,
			UserName: user,
			CreTime:  now,
			UpdTime:  now,
		},
	}
}
