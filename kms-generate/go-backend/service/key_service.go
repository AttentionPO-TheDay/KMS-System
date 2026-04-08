package service

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"io"
	"sync"
	"time"

	"key-service-generate/config"
	"key-service-generate/models"
	"key-service-generate/service/generator"
	"key-service-generate/utils"
)

const (
	ActionEnrollKey   = "ENROLL_KEY"
	ActionReenrollKey = "REENROLL_KEY"
)

var (
	currTimeStr string
	timeRwLock  sync.RWMutex
)

func init() {
	updateTimeStr()
	go func() {
		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()
		for range ticker {
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

type KeyManageService struct {
	eccGen        *generator.ECCGenerator
	ssclGen       *generator.SSCLGenerator
	kafkaProducer *utils.KafkaProducer
	saveChan      chan *models.KeyEnrollPayload
}

func NewKeyManageService() *KeyManageService {
	s := &KeyManageService{
		eccGen:        generator.GetECCGenerator(),
		ssclGen:       generator.GetSSCLGenerator(),
		kafkaProducer: utils.NewKafkaProducer(config.KafkaAddr, config.KafkaTopic),
		saveChan:      make(chan *models.KeyEnrollPayload, 100000),
	}

	for i := 0; i < 10; i++ {
		go s.kafkaWorker()
	}

	return s
}

func (s *KeyManageService) EnrollKey(km *models.Keymanage, rawPassword string) (string, error) {
	timeRwLock.RLock()
	nowStr := currTimeStr
	timeRwLock.RUnlock()
	km.CreTime = nowStr
	km.UpdTime = nowStr

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

	if err := s.sendToKafka(km, rawPassword, ActionEnrollKey); err != nil {
		return "", err
	}

	return km.KeyValue, nil
}

func (s *KeyManageService) sendToKafka(km *models.Keymanage, rawPassword, action string) error {
	payload := &models.KeyEnrollPayload{
		RawUser:      km.UserName,
		RawPassword:  rawPassword,
		ActionType:   action,
		GeneratedKey: *km,
	}

	select {
	case s.saveChan <- payload:
		return nil
	default:
		return errors.New("system busy, queue full")
	}
}

func (s *KeyManageService) kafkaWorker() {
	for payload := range s.saveChan {
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
