package utils

import (
	"log"
	"time"

	"github.com/IBM/sarama"
	"github.com/bytedance/sonic"
)

// KafkaProducer 封装 Sarama 的异步生产者
type KafkaProducer struct {
	producer sarama.AsyncProducer
	topic    string
}

// NewKafkaProducer 初始化
func NewKafkaProducer(addr string, topic string) *KafkaProducer {
	config := sarama.NewConfig()

	// 性能优化配置
	config.Producer.RequiredAcks = sarama.WaitForLocal
	config.Producer.Compression = sarama.CompressionSnappy
	config.Producer.Flush.Frequency = 500 * time.Millisecond
	config.Producer.Flush.Bytes = 16 * 1024
	config.Producer.Flush.Messages = 1000

	producer, err := sarama.NewAsyncProducer([]string{addr}, config)
	if err != nil {
		log.Fatalf("Failed to start Kafka producer: %v", err)
	}

	kp := &KafkaProducer{
		producer: producer,
		topic:    topic,
	}

	go kp.listenErrors()

	return kp
}

func (k *KafkaProducer) listenErrors() {
	for err := range k.producer.Errors() {
		log.Printf("[Kafka Error] %v\n", err)
	}
}

// SendAsync 异步发送消息
func (k *KafkaProducer) SendAsync(data interface{}) {
	bytesData, err := sonic.Marshal(data)
	if err != nil {
		log.Printf("[Serialization Error] %v\n", err)
		return
	}

	msg := &sarama.ProducerMessage{
		Topic: k.topic,
		Value: sarama.ByteEncoder(bytesData),
	}

	k.producer.Input() <- msg
}

func (k *KafkaProducer) Close() {
	if k.producer != nil {
		k.producer.AsyncClose()
	}
}
