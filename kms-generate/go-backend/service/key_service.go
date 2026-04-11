package service

import (
	"errors"
	"io"
	"net/http"
	"strings"
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

	if km.EncrytType != "无证书非对称加密" {
		return "", errors.New("only certless algorithms are supported")
	}

	switch km.EncrytName {
	case "SM2":
		resKm, err := s.eccGen.GenPartialKey(km.UserName, km.UA, km.KeyUse)
		if err != nil {
			return "", err
		}
		km.KeyValue = resKm.KeyValue
	case "SSCL":
		resKm, err := s.ssclGen.GenPartialKey(km.UserName, km.UA, km.KeyDomain, km.KeyUse)
		if err != nil {
			return "", err
		}
		km.KeyValue = resKm.KeyValue
	default:
		return "", errors.New("unsupported certless algorithm")
	}

	if err := s.sendToKafka(km, rawPassword, ActionEnrollKey); err != nil {
		return "", err
	}

	return km.KeyValue, nil
}

func (s *KeyManageService) Register(user, password string) error {
	payload := `{"user":"` + strings.ReplaceAll(user, `"`, `\"`) + `","password":"` + strings.ReplaceAll(password, `"`, `\"`) + `"}`
	resp, err := http.Post(config.JavaBackendBase+"/generate/user/register", "application/json", strings.NewReader(payload))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		body, _ := io.ReadAll(resp.Body)
		return errors.New(string(body))
	}

	return nil
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
	if encrytType != "无证书非对称加密" {
		return nil
	}
	if encrytName == "SSCL" {
		return s.ssclGen.GetComParam()
	}
	return nil
}
