package utils

import (
	"log"
	"strconv"
	"time"

	"github.com/IBM/sarama"
	"github.com/bytedance/sonic"
)

// KafkaProducer wraps Sarama AsyncProducer for high-throughput lifecycle events.
type KafkaProducer struct {
	updateProducer sarama.AsyncProducer
	revokeProducer sarama.AsyncProducer
	updateTopic     string
	revokeTopic     string
}

// NewKafkaProducer creates separate async producers for update and revoke topics.
func NewKafkaProducer(brokers string, updateTopic, revokeTopic string) *KafkaProducer {
	config := newSaramaConfig()

	updateProducer, err := sarama.NewAsyncProducer(splitBrokers(brokers), config)
	if err != nil {
		log.Fatalf("Failed to create update Kafka producer: %v", err)
	}

	revokeProducer, err := sarama.NewAsyncProducer(splitBrokers(brokers), config)
	if err != nil {
		log.Fatalf("Failed to create revoke Kafka producer: %v", err)
	}

	kp := &KafkaProducer{
		updateProducer: updateProducer,
		revokeProducer: revokeProducer,
		updateTopic:     updateTopic,
		revokeTopic:     revokeTopic,
	}

	go kp.listenErrors(updateProducer, "update")
	go kp.listenErrors(revokeProducer, "revoke")

	return kp
}

func newSaramaConfig() *sarama.Config {
	config := sarama.NewConfig()
	config.Producer.RequiredAcks = sarama.WaitForLocal
	config.Producer.Compression = sarama.CompressionSnappy
	config.Producer.Flush.Frequency = 500 * time.Millisecond
	config.Producer.Flush.Bytes = 16 * 1024
	config.Producer.Flush.Messages = 1000
	return config
}

func splitBrokers(brokers string) []string {
	// simple split by comma
	result := make([]string, 0)
	start := 0
	for i := 0; i <= len(brokers); i++ {
		if i == len(brokers) || brokers[i] == ',' {
			if start < i {
				result = append(result, brokers[start:i])
			}
			start = i + 1
		}
	}
	return result
}

func (k *KafkaProducer) listenErrors(p sarama.AsyncProducer, label string) {
	for err := range p.Errors() {
		log.Printf("[Kafka Error][%s] %v\n", label, err)
	}
}

// SendUpdate sends an UPDATE_KEY message to key_update_log topic, using keyId as message key.
func (k *KafkaProducer) SendUpdate(keyId int64, data interface{}) {
	bytesData, err := sonic.Marshal(data)
	if err != nil {
		log.Printf("[Serialization Error][update] %v\n", err)
		return
	}

	msg := &sarama.ProducerMessage{
		Topic: k.updateTopic,
		Key:   sarama.StringEncoder(strconv.FormatInt(keyId, 10)),
		Value: sarama.ByteEncoder(bytesData),
	}
	k.updateProducer.Input() <- msg
}

// SendRevoke sends a REVOKE_KEY message to key_revoke_log topic, using keyId as message key.
func (k *KafkaProducer) SendRevoke(keyId int64, data interface{}) {
	bytesData, err := sonic.Marshal(data)
	if err != nil {
		log.Printf("[Serialization Error][revoke] %v\n", err)
		return
	}

	msg := &sarama.ProducerMessage{
		Topic: k.revokeTopic,
		Key:   sarama.StringEncoder(strconv.FormatInt(keyId, 10)),
		Value: sarama.ByteEncoder(bytesData),
	}
	k.revokeProducer.Input() <- msg
}

// Close shuts down both producers.
func (k *KafkaProducer) Close() {
	if k.updateProducer != nil {
		k.updateProducer.AsyncClose()
	}
	if k.revokeProducer != nil {
		k.revokeProducer.AsyncClose()
	}
}
