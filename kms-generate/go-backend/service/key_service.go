package service

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
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

var pqAlgorithms = map[string]struct{}{
	"CL-Kyber":           {},
	"ML-KEM":             {},
	"Falcon":             {},
	"CL-Falcon":          {},
	"PQ_KYBER":           {},
	"PQ_FALCON":          {},
	"PQ_ML_KEM":          {},
	"PQ_CL_KYBER":        {},
	"PQ_CL_FALCON":       {},
	"PQ_CERTIFICATELESS": {},
}

var (
	currTimeStr string
	timeRwLock  sync.RWMutex
)

type demoGenerateRequest struct {
	KeyID            string                 `json:"key_id,omitempty"`
	CorrelationID    string                 `json:"correlation_id"`
	UserID           int64                  `json:"user_id,omitempty"`
	UserName         string                 `json:"user_name"`
	Algorithm        string                 `json:"algorithm"`
	Scheme           string                 `json:"scheme,omitempty"`
	KeyUse           string                 `json:"key_use,omitempty"`
	KeyDomain        string                 `json:"key_domain,omitempty"`
	PQMode           string                 `json:"pq_mode,omitempty"`
	OperatorMetadata map[string]interface{} `json:"operator_metadata,omitempty"`
}

type demoGenerateResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Msg     string `json:"msg"`
	Data    struct {
		DemoRecordID           string      `json:"demo_record_id"`
		Status                 string      `json:"status"`
		PQMode                 string      `json:"pq_mode"`
		KeyMaterialOrReference interface{} `json:"key_material_or_reference"`
	} `json:"data"`
}

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

func IsPQAlgorithm(algorithm string) bool {
	_, ok := pqAlgorithms[algorithm]
	return ok
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

	switch {
	case km.EncrytType == "无证书非对称加密" && km.EncrytName == "SM2":
		resKm, err := s.eccGen.GenPartialKey(km.UserName, km.UA, km.KeyUse)
		if err != nil {
			return "", err
		}
		km.KeyValue = resKm.KeyValue
	case km.EncrytType == "无证书非对称加密" && km.EncrytName == "SSCL":
		resKm, err := s.ssclGen.GenPartialKey(km.UserName, km.UA, km.KeyDomain, km.KeyUse)
		if err != nil {
			return "", err
		}
		km.KeyValue = resKm.KeyValue
	case km.EncrytType == "无证书非对称加密" && IsPQAlgorithm(km.EncrytName):
		if strings.TrimSpace(km.PQMode) == "" {
			km.PQMode = "demo_generated"
		}
		if km.PQMode == "strict_certificateless" {
			return "", errors.New("strict certificateless PQ generation requires user/node local secret material and is not implemented in this thin demo API")
		}
		if km.PQMode != "demo_generated" {
			return "", errors.New("pq_mode must be demo_generated or strict_certificateless")
		}
		if err := s.generateDemoRecordKey(km); err != nil {
			return "", err
		}
	default:
		return "", errors.New("unsupported key generation algorithm")
	}

	if err := s.sendToKafka(km, rawPassword, ActionEnrollKey); err != nil {
		return "", err
	}

	return km.KeyValue, nil
}

func (s *KeyManageService) GeneratePartialKey(encrytName, userName, ua, keyDomain, keyUse string) (string, error) {
	switch encrytName {
	case "SM2":
		resKm, err := s.eccGen.GenPartialKey(userName, ua, keyUse)
		if err != nil {
			return "", err
		}
		return resKm.KeyValue, nil
	case "SSCL":
		resKm, err := s.ssclGen.GenPartialKey(userName, ua, keyDomain, keyUse)
		if err != nil {
			return "", err
		}
		return resKm.KeyValue, nil
	default:
		return "", errors.New("partial key algorithm must be SM2 or SSCL")
	}
}

func (s *KeyManageService) generateDemoRecordKey(km *models.Keymanage) error {
	correlationID := fmt.Sprintf("kms-%s-%d", strings.ReplaceAll(km.UserName, " ", "_"), time.Now().UnixNano())
	payload := demoGenerateRequest{
		CorrelationID: correlationID,
		UserID:        km.UserID,
		UserName:      km.UserName,
		Algorithm:     km.EncrytName,
		Scheme:        km.EncrytType,
		KeyUse:        km.KeyUse,
		KeyDomain:     km.KeyDomain,
		PQMode:        km.PQMode,
		OperatorMetadata: map[string]interface{}{
			"key_name":    km.KeyName,
			"auto_update": km.AutoUpdate,
		},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	url := strings.TrimRight(config.DemoBackendBase, "/") + "/kms/generate-record/"
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("demo backend unavailable: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("demo backend generation failed [%d]: %s", resp.StatusCode, string(respBody))
	}

	var demoResp demoGenerateResponse
	if err := json.Unmarshal(respBody, &demoResp); err != nil {
		return fmt.Errorf("demo backend returned invalid response: %w", err)
	}
	if demoResp.Code != 0 && demoResp.Code != http.StatusOK {
		msg := demoResp.Message
		if msg == "" {
			msg = demoResp.Msg
		}
		return fmt.Errorf("demo backend generation failed: %s", msg)
	}

	km.DemoRecordID = demoResp.Data.DemoRecordID
	km.DemoResultStatus = demoResp.Data.Status
	if demoResp.Data.PQMode == "" {
		demoResp.Data.PQMode = km.PQMode
	}
	keyValue, err := json.Marshal(demoResp.Data)
	if err != nil {
		return err
	}
	km.KeyValue = string(keyValue)
	return nil
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
		if err := s.kafkaProducer.SendAsync(payload); err != nil {
			log.Printf("[WARN] failed to publish generate payload for user %s: %v", payload.RawUser, err)
		}
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
