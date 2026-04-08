package service

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"io"
	"sync"
	"time"

	"key-service/models"
	"key-service/service/generator"
	"key-service/utils"
)

const (
	KafkaAddr  = "kafka:9092"
	KafkaTopic = "go_key_manage_log"
)

// 定义操作类型常量 (对应 Java 的 Requestor.Permission)
const (
	ActionEnrollKey    = "ENROLL_KEY"
	ActionReenrollKey  = "REENROLL_KEY"
	ActionUpdateKey    = "UPDATE_KEY"
	ActionUnsuspendKey = "UNSUSPEND_KEY"
	ActionRevokeKey    = "REVOKE_KEY"
)

// --- 全局时间缓存 (保持不变) ---
var (
	currTimeStr string
	timeRwLock  sync.RWMutex
)

func init() {
	updateTimeStr()
	go func() {
		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()
		for range ticker.C {
			updateTimeStr()
		}
	}()
}

func updateTimeStr() {
	now := time.Now().Format("2006-01-02 15:04:05")
	timeRwLock.Lock()
	currTimeStr = now
	timeRwLock.Unlock()
}

// ----------------------------------------

type KeyManageService struct {
	eccGen  *generator.ECCGenerator
	ssclGen *generator.SSCLGenerator

	// Kafka 生产者工具类
	kafkaProducer *utils.KafkaProducer

	// 内存缓冲通道
	saveChan chan *models.KeyEnrollPayload
}

func NewKeyManageService() *KeyManageService {
	s := &KeyManageService{
		eccGen:        generator.GetECCGenerator(),
		ssclGen:       generator.GetSSCLGenerator(),
		kafkaProducer: utils.NewKafkaProducer(KafkaAddr, KafkaTopic),

		// 初始化通道，缓冲区保持较大
		saveChan: make(chan *models.KeyEnrollPayload, 100000),
	}

	// 启动 Worker
	for i := 0; i < 10; i++ {
		go s.kafkaWorker()
	}

	return s
}

// EnrollKey 核心业务方法：密钥生成 (需要本地计算)
func (s *KeyManageService) EnrollKey(km *models.Keymanage, rawPassword string) (string, error) {
	// 1. 设置时间
	timeRwLock.RLock()
	nowStr := currTimeStr
	timeRwLock.RUnlock()
	km.CreTime = nowStr
	km.UpdTime = nowStr

	// 2. 生成密钥逻辑 (计算密集型)
	if km.EncrytType == "无证书非对称加密" {
		switch km.EncrytName {
		case "SM2":
			resKm, err := s.eccGen.GenPartialKey(km.UserName, km.UA)
			if err != nil {
				return "", err
			}
			km.KeyValue = resKm.KeyValue
		case "SSCL":
			resKm, err := s.ssclGen.GenPartialKey(km.UserName, km.UA, km.KeyDomain)
			if err != nil {
				return "", err
			}
			km.KeyValue = resKm.KeyValue
		}
	} else if km.EncrytType == "对称加密" && km.EncrytName == "AES" {
		keyBuf := make([]byte, 32)
		if _, err := io.ReadFull(rand.Reader, keyBuf); err != nil {
			return "", err
		}
		km.KeyValue = hex.EncodeToString(keyBuf)
	} else {
		km.KeyValue = "demo"
	}

	// 3. 发送 Kafka (Action: ENROLL)
	// 这里将生成的 KeyValue 一并发出
	if err := s.sendToKafka(km, rawPassword, ActionEnrollKey); err != nil {
		return "", err
	}

	// 返回给前端生成的 KeyValue
	return km.KeyValue, nil
}

// UpdateKey 密钥更新/轮换 (轻量级转发)
// 前端只传 KeyId，Go 不负责生成，直接转发给 Java 处理
func (s *KeyManageService) UpdateKey(km *models.Keymanage, rawPassword string) (string, error) {
	// 1. 不需要生成密钥，因为 Go 没有 uA
	// 2. 直接发送 Kafka (Action: UPDATE)
	// Java 收到后会：查库获取 uA -> 重新生成密钥 -> 存库(v+1) -> 上链
	if err := s.sendToKafka(km, rawPassword, ActionUpdateKey); err != nil {
		return "", err
	}

	return "processing_async", nil
}

// RevokeKey 密钥回收 (轻量级转发)
func (s *KeyManageService) RevokeKey(keyId int64, user, rawPassword string) error {
	km := &models.Keymanage{
		KeyID:    keyId,
		UserName: user,
	}
	// 发送 Kafka (Action: REVOKE)
	return s.sendToKafka(km, rawPassword, ActionRevokeKey)
}

// =================================================================
// 辅助方法
// =================================================================

// sendToKafka 统一封装 Kafka 发送逻辑
func (s *KeyManageService) sendToKafka(km *models.Keymanage, rawPassword, action string) error {
	payload := &models.KeyEnrollPayload{
		RawUser:      km.UserName,
		RawPassword:  rawPassword,
		ActionType:   action,
		GeneratedKey: *km,
	}

	select {
	case s.saveChan <- payload: // 发送 payload
		// 成功入队
		return nil
	default:
		return errors.New("system busy, queue full")
	}
}

// kafkaWorker 从 Channel 取数据并调用 Utils 发送
func (s *KeyManageService) kafkaWorker() {
	for payload := range s.saveChan {
		// 直接调用工具类发送
		s.kafkaProducer.SendAsync(payload)
	}
}

func (s *KeyManageService) Close() {
	if s.kafkaProducer != nil {
		s.kafkaProducer.Close()
	}
}

func (s *KeyManageService) GetComParam(encrytType, encrytName string) map[string]interface{} {
	if encrytType == "无证书非对称加密" {
		if encrytName == "SSCL" {
			return s.ssclGen.GetComParam()
		}
	}
	return nil
}
