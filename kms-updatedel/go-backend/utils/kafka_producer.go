package utils

import (
	"errors"
	"log"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/IBM/sarama"
	"github.com/bytedance/sonic"
)

var (
	ErrKafkaNotReady       = errors.New("kafka producer not ready")
	ErrKafkaProducerClosed = errors.New("kafka producer closed")
)

type producerSlot struct {
	label        string
	topic        string
	producer     sarama.AsyncProducer
	reconnectCh  chan struct{}
	errorHandler func(error)
}

// KafkaProducer wraps Sarama AsyncProducer for high-throughput lifecycle events.
type KafkaProducer struct {
	mu      sync.RWMutex
	brokers []string
	stopCh  chan struct{}
	stopped bool
	update  *producerSlot
	revoke  *producerSlot
}

// NewKafkaProducer creates separate async producers for update and revoke topics.
func NewKafkaProducer(brokers string, updateTopic, revokeTopic string) *KafkaProducer {
	kp := &KafkaProducer{
		brokers: splitBrokers(brokers),
		stopCh:  make(chan struct{}),
		update: &producerSlot{
			label:       "update",
			topic:       updateTopic,
			reconnectCh: make(chan struct{}, 1),
		},
		revoke: &producerSlot{
			label:       "revoke",
			topic:       revokeTopic,
			reconnectCh: make(chan struct{}, 1),
		},
	}

	go kp.connectionLoop(kp.update)
	go kp.connectionLoop(kp.revoke)
	kp.requestReconnect(kp.update)
	kp.requestReconnect(kp.revoke)

	return kp
}

func (k *KafkaProducer) SetErrorHandlers(updateHandler, revokeHandler func(error)) {
	k.mu.Lock()
	defer k.mu.Unlock()
	k.update.errorHandler = updateHandler
	k.revoke.errorHandler = revokeHandler
}

func newSaramaConfig() *sarama.Config {
	config := sarama.NewConfig()
	config.Producer.RequiredAcks = sarama.WaitForLocal
	config.Producer.Compression = sarama.CompressionSnappy
	config.Producer.Flush.Frequency = 500 * time.Millisecond
	config.Producer.Flush.Bytes = 16 * 1024
	config.Producer.Flush.Messages = 1000
	config.Producer.Return.Errors = true
	return config
}

func splitBrokers(brokers string) []string {
	parts := strings.Split(brokers, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		broker := strings.TrimSpace(part)
		if broker != "" {
			result = append(result, broker)
		}
	}
	return result
}

func (k *KafkaProducer) requestReconnect(slot *producerSlot) {
	select {
	case slot.reconnectCh <- struct{}{}:
	default:
	}
}

func (k *KafkaProducer) connectionLoop(slot *producerSlot) {
	backoff := time.Second

	for {
		select {
		case <-k.stopCh:
			return
		case <-slot.reconnectCh:
		}

		if k.isReady(slot) {
			continue
		}

		for !k.isReady(slot) {
			err := k.connect(slot)
			if err == nil {
				backoff = time.Second
				log.Printf("[INFO] Kafka producer connected for %s topic %s", slot.label, slot.topic)
				break
			}
			if errors.Is(err, ErrKafkaProducerClosed) {
				return
			}

			log.Printf("[WARN] Kafka producer unavailable for %s topic %s: %v. Retrying in %s.", slot.label, slot.topic, err, backoff)
			timer := time.NewTimer(backoff)
			select {
			case <-k.stopCh:
				timer.Stop()
				return
			case <-timer.C:
			}

			if backoff < 30*time.Second {
				backoff *= 2
				if backoff > 30*time.Second {
					backoff = 30 * time.Second
				}
			}
		}
	}
}

func (k *KafkaProducer) connect(slot *producerSlot) error {
	producer, err := sarama.NewAsyncProducer(k.brokers, newSaramaConfig())
	if err != nil {
		return err
	}

	k.mu.Lock()
	if k.stopped {
		k.mu.Unlock()
		producer.AsyncClose()
		return ErrKafkaProducerClosed
	}
	if slot.producer != nil {
		k.mu.Unlock()
		producer.AsyncClose()
		return nil
	}
	slot.producer = producer
	k.mu.Unlock()

	go k.listenErrors(slot, producer)
	return nil
}

func (k *KafkaProducer) listenErrors(slot *producerSlot, producer sarama.AsyncProducer) {
	for err := range producer.Errors() {
		log.Printf("[Kafka Error][%s] %v", slot.label, err)
		if handler := k.errorHandler(slot); handler != nil {
			handler(err)
		}
	}

	k.mu.Lock()
	if !k.stopped && slot.producer == producer {
		slot.producer = nil
		k.mu.Unlock()
		k.requestReconnect(slot)
		return
	}
	k.mu.Unlock()
}

func (k *KafkaProducer) errorHandler(slot *producerSlot) func(error) {
	k.mu.RLock()
	defer k.mu.RUnlock()
	return slot.errorHandler
}

func (k *KafkaProducer) currentProducer(slot *producerSlot) sarama.AsyncProducer {
	k.mu.RLock()
	defer k.mu.RUnlock()
	if k.stopped {
		return nil
	}
	return slot.producer
}

func (k *KafkaProducer) markDisconnected(slot *producerSlot, producer sarama.AsyncProducer) {
	k.mu.Lock()
	if !k.stopped && slot.producer == producer {
		slot.producer = nil
		k.mu.Unlock()
		k.requestReconnect(slot)
		return
	}
	k.mu.Unlock()
}

func (k *KafkaProducer) isReady(slot *producerSlot) bool {
	return k.currentProducer(slot) != nil
}

func (k *KafkaProducer) IsReady() bool {
	return k.isReady(k.update) && k.isReady(k.revoke)
}

// SendUpdate sends an UPDATE_KEY message to key_update_log topic, using keyId as message key.
func (k *KafkaProducer) SendUpdate(keyId int64, data interface{}) error {
	bytesData, err := sonic.Marshal(data)
	if err != nil {
		return err
	}
	return k.send(k.update, keyId, bytesData)
}

// SendRevoke sends a REVOKE_KEY message to key_revoke_log topic, using keyId as message key.
func (k *KafkaProducer) SendRevoke(keyId int64, data interface{}) error {
	bytesData, err := sonic.Marshal(data)
	if err != nil {
		return err
	}
	return k.send(k.revoke, keyId, bytesData)
}

func (k *KafkaProducer) send(slot *producerSlot, keyId int64, bytesData []byte) (err error) {
	producer := k.currentProducer(slot)
	if producer == nil {
		return ErrKafkaNotReady
	}

	msg := &sarama.ProducerMessage{
		Topic: slot.topic,
		Key:   sarama.StringEncoder(strconv.FormatInt(keyId, 10)),
		Value: sarama.ByteEncoder(bytesData),
	}

	defer func() {
		if recover() != nil {
			err = ErrKafkaNotReady
			k.markDisconnected(slot, producer)
		}
	}()

	producer.Input() <- msg
	return nil
}

// Close shuts down both producers.
func (k *KafkaProducer) Close() {
	k.mu.Lock()
	if k.stopped {
		k.mu.Unlock()
		return
	}
	k.stopped = true
	close(k.stopCh)
	updateProducer := k.update.producer
	revokeProducer := k.revoke.producer
	k.update.producer = nil
	k.revoke.producer = nil
	k.mu.Unlock()

	if updateProducer != nil {
		updateProducer.AsyncClose()
	}
	if revokeProducer != nil {
		revokeProducer.AsyncClose()
	}
}
