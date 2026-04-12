package utils

import (
	"encoding/json"
	"errors"
	"log"
	"sync"
	"time"

	"github.com/IBM/sarama"
)

var (
	ErrKafkaNotReady       = errors.New("kafka producer not ready")
	ErrKafkaProducerClosed = errors.New("kafka producer closed")
)

// KafkaProducer 封装 Sarama 的异步生产者，并在 Kafka 不可用时后台重连。
type KafkaProducer struct {
	mu          sync.RWMutex
	producer    sarama.AsyncProducer
	topic       string
	brokers     []string
	stopCh      chan struct{}
	reconnectCh chan struct{}
	stopped     bool
}

// NewKafkaProducer 初始化一个可后台重连的 Kafka producer。
func NewKafkaProducer(addr string, topic string) *KafkaProducer {
	kp := &KafkaProducer{
		topic:       topic,
		brokers:     []string{addr},
		stopCh:      make(chan struct{}),
		reconnectCh: make(chan struct{}, 1),
	}

	go kp.connectionLoop()
	kp.requestReconnect()

	return kp
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

func (k *KafkaProducer) requestReconnect() {
	select {
	case k.reconnectCh <- struct{}{}:
	default:
	}
}

func (k *KafkaProducer) connectionLoop() {
	backoff := time.Second

	for {
		select {
		case <-k.stopCh:
			return
		case <-k.reconnectCh:
		}

		if k.IsReady() {
			continue
		}

		for !k.IsReady() {
			err := k.connect()
			if err == nil {
				backoff = time.Second
				log.Printf("[INFO] Kafka producer connected for topic %s", k.topic)
				break
			}
			if errors.Is(err, ErrKafkaProducerClosed) {
				return
			}

			log.Printf("[WARN] Kafka producer unavailable for topic %s: %v. Retrying in %s.", k.topic, err, backoff)
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

func (k *KafkaProducer) connect() error {
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
	if k.producer != nil {
		k.mu.Unlock()
		producer.AsyncClose()
		return nil
	}
	k.producer = producer
	k.mu.Unlock()

	go k.listenErrors(producer)
	return nil
}

func (k *KafkaProducer) listenErrors(producer sarama.AsyncProducer) {
	for err := range producer.Errors() {
		log.Printf("[Kafka Error] %v", err)
	}

	k.mu.Lock()
	if !k.stopped && k.producer == producer {
		k.producer = nil
		k.mu.Unlock()
		k.requestReconnect()
		return
	}
	k.mu.Unlock()
}

func (k *KafkaProducer) currentProducer() sarama.AsyncProducer {
	k.mu.RLock()
	defer k.mu.RUnlock()
	if k.stopped {
		return nil
	}
	return k.producer
}

func (k *KafkaProducer) markDisconnected(producer sarama.AsyncProducer) {
	k.mu.Lock()
	if !k.stopped && k.producer == producer {
		k.producer = nil
		k.mu.Unlock()
		k.requestReconnect()
		return
	}
	k.mu.Unlock()
}

func (k *KafkaProducer) IsReady() bool {
	return k.currentProducer() != nil
}

// SendAsync 异步发送消息。
func (k *KafkaProducer) SendAsync(data interface{}) (err error) {
	bytesData, err := json.Marshal(data)
	if err != nil {
		return err
	}

	producer := k.currentProducer()
	if producer == nil {
		return ErrKafkaNotReady
	}

	msg := &sarama.ProducerMessage{
		Topic: k.topic,
		Value: sarama.ByteEncoder(bytesData),
	}

	defer func() {
		if recover() != nil {
			err = ErrKafkaNotReady
			k.markDisconnected(producer)
		}
	}()

	producer.Input() <- msg
	return nil
}

func (k *KafkaProducer) Close() {
	k.mu.Lock()
	if k.stopped {
		k.mu.Unlock()
		return
	}
	k.stopped = true
	close(k.stopCh)
	producer := k.producer
	k.producer = nil
	k.mu.Unlock()

	if producer != nil {
		producer.AsyncClose()
	}
}
