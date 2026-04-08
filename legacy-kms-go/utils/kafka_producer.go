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

	// --- 性能优化配置 ---
	// 1. 吞吐量优先：WaitForLocal 相比 WaitForAll 性能提升巨大
	config.Producer.RequiredAcks = sarama.WaitForLocal

	// 2. 压缩：Snappy 压缩速度极快，CPU 占用低，能大幅降低带宽压力
	config.Producer.Compression = sarama.CompressionSnappy

	// 3. 批处理：这是高吞吐的关键，让 Sarama 在本地聚合消息后再发送
	config.Producer.Flush.Frequency = 500 * time.Millisecond // 每 500ms 强刷一次
	config.Producer.Flush.Bytes = 16 * 1024                  // 或者积累满 16KB 刷一次
	config.Producer.Flush.Messages = 1000                    // 或者积累满 1000 条刷一次

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
		// 生产环境建议降级处理或采样打印，防止错误日志本身把磁盘打爆
		log.Printf("[Kafka Error] %v\n", err)
	}
}

// SendAsync 异步发送消息
// data: 任意结构体
func (k *KafkaProducer) SendAsync(data interface{}) {
	// 1. 使用 Sonic 进行极速序列化
	// Sonic 的 Marshal 性能极高，通常在纳秒级别
	bytesData, err := sonic.Marshal(data)
	if err != nil {
		log.Printf("[Serialization Error] %v\n", err)
		return
	}

	// 2. 构造消息
	msg := &sarama.ProducerMessage{
		Topic: k.topic,
		Value: sarama.ByteEncoder(bytesData),
	}

	// 3. 非阻塞发送
	// 注意：Input() 通道有缓冲，如果 Kafka 挂了或网络极慢导致本地缓冲满，这里会阻塞
	// 为了极致健壮性，可以使用 select + default 丢弃策略，但一般情况下直接发即可
	k.producer.Input() <- msg
}

func (k *KafkaProducer) Close() {
	if k.producer != nil {
		k.producer.AsyncClose()
	}
}
