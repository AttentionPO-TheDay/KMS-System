package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gofiber/fiber/v2"
)

const keyIDPlaceholder = "{{KEY_ID}}"

type Scenario struct {
	ID              string            `json:"id"`
	Name            string            `json:"name"`
	TargetTPS       float64           `json:"targetTps"`
	TargetOperator  string            `json:"targetOperator"`
	Method          string            `json:"method"`
	BaseURL         string            `json:"baseUrl"`
	Path            string            `json:"path"`
	DurationSeconds int               `json:"durationSeconds"`
	Threads         int               `json:"threads"`
	Connections     int               `json:"connections"`
	Headers         map[string]string `json:"headers"`
	BodyTemplate    string            `json:"bodyTemplate"`
	MetricKind      string            `json:"metricKind,omitempty"`
	MetricTarget    float64           `json:"metricTarget,omitempty"`
	MetricOperator  string            `json:"metricOperator,omitempty"`
	Description     string            `json:"description"`
	Notes           []string          `json:"notes,omitempty"`
	PreparedKeyIDs  []int64           `json:"-"`
	GeneratedAfter  time.Time         `json:"-"`
	SourceRunID     string            `json:"-"`
}

type AcceptanceCriterion struct {
	ID             string   `json:"id"`
	Category       string   `json:"category"`
	Title          string   `json:"title"`
	Requirement    string   `json:"requirement"`
	Kind           string   `json:"kind"`
	Target         float64  `json:"target,omitempty"`
	Operator       string   `json:"operator,omitempty"`
	Unit           string   `json:"unit,omitempty"`
	ScenarioID     string   `json:"scenarioId,omitempty"`
	CaseIDs        []string `json:"caseIds,omitempty"`
	ExecutionScope string   `json:"executionScope"`
	EvidenceSource string   `json:"evidenceSource"`
	Notes          []string `json:"notes,omitempty"`
}

type AcceptanceEvidenceRequest struct {
	CriterionID string  `json:"criterionId"`
	Value       float64 `json:"value"`
	Evidence    string  `json:"evidence"`
	MeasuredAt  string  `json:"measuredAt"`
}

type AcceptanceEvidence struct {
	ID               string  `json:"id"`
	CriterionID      string  `json:"criterionId"`
	Value            float64 `json:"value"`
	Unit             string  `json:"unit"`
	Operator         string  `json:"operator"`
	Target           float64 `json:"target"`
	Passed           bool    `json:"passed"`
	Evidence         string  `json:"evidence"`
	MeasuredAt       string  `json:"measuredAt"`
	RecordedAt       string  `json:"recordedAt"`
	Verified         bool    `json:"verified"`
	Source           string  `json:"source,omitempty"`
	NodeCode         string  `json:"nodeCode,omitempty"`
	NodeName         string  `json:"nodeName,omitempty"`
	TargetNodeCode   string  `json:"targetNodeCode,omitempty"`
	PoolID           string  `json:"poolId,omitempty"`
	Requested        int     `json:"requested,omitempty"`
	Generated        int     `json:"generated,omitempty"`
	Failed           int     `json:"failed,omitempty"`
	LocalMs          float64 `json:"localMs,omitempty"`
	LocalThroughput  float64 `json:"localThroughput,omitempty"`
	ServerMs         float64 `json:"serverMs,omitempty"`
	ServerThroughput float64 `json:"serverThroughput,omitempty"`
}

type acceptanceEvidenceEnvelope struct {
	Code int                  `json:"code"`
	Data []AcceptanceEvidence `json:"data"`
}

type persistedAcceptanceEvidence struct {
	Items []*AcceptanceEvidence `json:"items"`
}

type RunRequest struct {
	ScenarioID  string   `json:"scenarioId"`
	Threads     int      `json:"threads"`
	Connections int      `json:"connections"`
	DurationSec int      `json:"durationSeconds"`
	BaseURL     string   `json:"baseUrl"`
	Path        string   `json:"path"`
	Headers     []string `json:"headers"`
	Body        string   `json:"body"`
	WrkPath     string   `json:"wrkPath"`
}

type HealthResponse struct {
	Status             string `json:"status"`
	Service            string `json:"service"`
	WrkAvailable       bool   `json:"wrkAvailable"`
	WrkPath            string `json:"wrkPath,omitempty"`
	SecurityScriptPath string `json:"securityScriptPath,omitempty"`
	SecurityExecutable string `json:"securityExecutable,omitempty"`
	SecurityAvailable  bool   `json:"securityAvailable"`
	DataDir            string `json:"dataDir"`
	Now                string `json:"now"`
	AcceptanceUser     string `json:"acceptanceUser"`
	GenerateKeyPoolURL string `json:"generateKeyPoolUrl"`
	LifecycleVerifyURL string `json:"lifecycleVerifyUrl"`
	LifecycleProofURL  string `json:"lifecycleProofUrl"`
}

type SecurityRunRequest struct {
	CaseID string `json:"caseId"`
}

type SecurityRequestTrace struct {
	Name         string `json:"name"`
	Method       string `json:"method"`
	URL          string `json:"url"`
	StatusCode   int    `json:"statusCode,omitempty"`
	Outcome      string `json:"outcome,omitempty"`
	Message      string `json:"message,omitempty"`
	ResponseBody string `json:"responseBody,omitempty"`
	RecordedAt   string `json:"recordedAt,omitempty"`
	DurationMs   int64  `json:"durationMs"`
}

type SecurityRunResult struct {
	ID                 string                 `json:"id"`
	CaseID             string                 `json:"caseId"`
	Status             string                 `json:"status"`
	Stage              string                 `json:"stage,omitempty"`
	Verdict            string                 `json:"verdict"`
	Passed             bool                   `json:"passed"`
	StartedAt          string                 `json:"startedAt"`
	FinishedAt         string                 `json:"finishedAt,omitempty"`
	Summary            string                 `json:"summary,omitempty"`
	Error              string                 `json:"error,omitempty"`
	Notes              []string               `json:"notes,omitempty"`
	Requests           []SecurityRequestTrace `json:"requests,omitempty"`
	ProbeSteps         []SecurityProbeStep    `json:"probeSteps,omitempty"`
	RawOutput          string                 `json:"rawOutput,omitempty"`
	ExpectedCode       string                 `json:"expectedCode,omitempty"`
	ActualCode         string                 `json:"actualCode,omitempty"`
	LegalControlPassed bool                   `json:"legalControlPassed"`
	EvidenceVersion    int                    `json:"evidenceVersion,omitempty"`
	TestInput          string                 `json:"testInput,omitempty"`
	ValidationRule     string                 `json:"validationRule,omitempty"`
	ExpectedReason     string                 `json:"expectedReason,omitempty"`
	ActualReason       string                 `json:"actualReason,omitempty"`
	ReasonMatched      bool                   `json:"reasonMatched"`
	ProtocolPassed     bool                   `json:"protocolPassed"`
	AlgorithmEvidence  *AlgorithmEvidence     `json:"algorithmEvidence,omitempty"`
	QuantumEvidence    *QuantumEvidence       `json:"quantumEvidence,omitempty"`
}

type ProofRunRequest struct {
	BatchSize        int    `json:"batchSize"`
	TreeFanout       int    `json:"treeFanout"`
	ProofMode        string `json:"proofMode"`
	LifecycleBaseURL string `json:"lifecycleBaseUrl"`
}

type ProofCheck struct {
	Name    string   `json:"name"`
	Passed  bool     `json:"passed"`
	Message string   `json:"message"`
	Details []string `json:"details,omitempty"`
}

type ProofRecord struct {
	RecordID        int64  `json:"recordId"`
	KeyID           int64  `json:"keyId"`
	KeyVersion      int    `json:"keyVersion"`
	BatchID         string `json:"batchId"`
	ParentBatchID   string `json:"parentBatchId"`
	RootBatchID     string `json:"rootBatchId"`
	TreePath        string `json:"treePath"`
	TreeLevel       int    `json:"treeLevel"`
	NodeIndex       int    `json:"nodeIndex"`
	ExpectedCount   int    `json:"expectedCount"`
	TreeFanout      int    `json:"treeFanout"`
	ProofMode       string `json:"proofMode"`
	Commitment      string `json:"commitment"`
	ConsistencyHash string `json:"consistencyHash"`
	BatchRoot       string `json:"batchRoot"`
	VerifyStatus    string `json:"verifyStatus"`
	VerifyMessage   string `json:"verifyMessage"`
	ResultStatus    string `json:"resultStatus"`
	ChainStatus     string `json:"chainStatus"`
}

type ProofSummary struct {
	BatchID                     string `json:"batchId"`
	ActionType                  string `json:"actionType"`
	ExpectedCount               int    `json:"expectedCount"`
	ReceivedCount               int    `json:"receivedCount"`
	BatchRoot                   string `json:"batchRoot"`
	VerifyStatus                string `json:"verifyStatus"`
	VerifyMessage               string `json:"verifyMessage"`
	AllCommitmentsPresent       bool   `json:"allCommitmentsPresent"`
	AllConsistencyHashesPresent bool   `json:"allConsistencyHashesPresent"`
	DuplicateNodeIndex          bool   `json:"duplicateNodeIndex"`
}

type lifecycleProofResponse struct {
	Summary ProofSummary  `json:"summary"`
	Data    []ProofRecord `json:"data"`
}

type batchUpdateResponse struct {
	BatchID   string `json:"batch_id"`
	Accepted  int    `json:"accepted"`
	Duplicate int    `json:"duplicates"`
	Total     int    `json:"total"`
	Status    string `json:"status"`
	Message   string `json:"msg"`
}

type ProofRunResult struct {
	ID         string        `json:"id"`
	Status     string        `json:"status"`
	Passed     bool          `json:"passed"`
	StartedAt  string        `json:"startedAt"`
	FinishedAt string        `json:"finishedAt,omitempty"`
	BatchID    string        `json:"batchId,omitempty"`
	BatchSize  int           `json:"batchSize"`
	TreeFanout int           `json:"treeFanout"`
	ProofMode  string        `json:"proofMode"`
	Summary    ProofSummary  `json:"summary"`
	TreeCheck  ProofCheck    `json:"treeCheck"`
	ProofCheck ProofCheck    `json:"proofCheck"`
	Records    []ProofRecord `json:"records,omitempty"`
	Notes      []string      `json:"notes,omitempty"`
	Error      string        `json:"error,omitempty"`
}

type RunSummary struct {
	RequestsPerSec           float64 `json:"requestsPerSec"`
	SuccessfulRequestsPerSec float64 `json:"successfulRequestsPerSec"`
	AvgLatencyMs             float64 `json:"avgLatencyMs"`
	P99LatencyMs             float64 `json:"p99LatencyMs"`
	TransferPerSec           string  `json:"transferPerSec,omitempty"`
	TotalRequests            int64   `json:"totalRequests"`
	ReadBytes                string  `json:"readBytes,omitempty"`
	Non2xxResponses          int64   `json:"non2xxResponses"`
	SocketErrors             int64   `json:"socketErrors"`
	ErrorCount               int64   `json:"errorCount"`
	SuccessRate              float64 `json:"successRate"`
	RawOutput                string  `json:"rawOutput"`
}

type MetricCheck struct {
	Kind       string  `json:"kind,omitempty"`
	Value      float64 `json:"value,omitempty"`
	Target     float64 `json:"target,omitempty"`
	Operator   string  `json:"operator,omitempty"`
	Passed     bool    `json:"passed"`
	Source     string  `json:"source,omitempty"`
	Message    string  `json:"message,omitempty"`
	Collected  bool    `json:"collected"`
	Enforced   bool    `json:"enforced"`
	ReportedAt string  `json:"reportedAt,omitempty"`
}

type ExecutionStage struct {
	At    string `json:"at"`
	Label string `json:"label"`
}

type RunResult struct {
	ID          string               `json:"id"`
	ScenarioID  string               `json:"scenarioId"`
	Scenario    string               `json:"scenario"`
	Status      string               `json:"status"`
	Stage       string               `json:"stage,omitempty"`
	Stages      []ExecutionStage     `json:"stages,omitempty"`
	StartedAt   string               `json:"startedAt"`
	FinishedAt  string               `json:"finishedAt,omitempty"`
	TargetTPS   float64              `json:"targetTps"`
	PassedTPS   bool                 `json:"passedTps"`
	WrkCommand  []string             `json:"wrkCommand"`
	Summary     RunSummary           `json:"summary"`
	MetricCheck MetricCheck          `json:"metricCheck"`
	Notes       []string             `json:"notes,omitempty"`
	Error       string               `json:"error,omitempty"`
	Abnormal    *abnormalEvidence    `json:"abnormalEvidence,omitempty"`
	FixedUpdate *fixedUpdateEvidence `json:"fixedUpdateEvidence,omitempty"`
	Symmetric   *symmetricEvidence   `json:"symmetricEvidence,omitempty"`
	Generation  *generationEvidence  `json:"generationEvidence,omitempty"`
}

type persistedRuns struct {
	Runs []*RunResult `json:"runs"`
}

type internalKeyRecord struct {
	KeyID      int64  `json:"keyId"`
	UserName   string `json:"userName"`
	Status     string `json:"status"`
	CreatedAt  string `json:"createdAt"`
	KeyDomain  string `json:"keyDomain"`
	UA         string `json:"ua"`
	EncrytName string `json:"encrytName"`
	KeyName    string `json:"keyName"`
}

type internalGenerateResponse struct {
	Data []internalKeyRecord `json:"data"`
}

type internalVerifyRecord struct {
	KeyID          int64  `json:"keyId"`
	Exists         bool   `json:"exists"`
	Status         string `json:"status"`
	ChainStatus    string `json:"chainStatus"`
	UpdatedAt      string `json:"updatedAt"`
	Version        *int   `json:"version"`
	UserName       string `json:"userName"`
	KeyDomain      string `json:"keyDomain"`
	MaterialDigest string `json:"materialDigest,omitempty"`
}

type internalVerifyResponse struct {
	Data []internalVerifyRecord `json:"data"`
}

type acceptanceConfig struct {
	AbnormalRevocationURL    string
	SymmetricReclamationURL  string
	GenerateInternalToken    string
	GenerateKeyPoolURL       string
	LifecycleVerifyURL       string
	LifecycleProofURL        string
	PreallocationEvidenceURL string
	GenerateJavaBaseURL      string
	LifecycleJavaBaseURL     string
	AcceptanceUser           string
	AttackUserName           string
	AttackUserPassword       string
	AttackAdminUserName      string
	AttackAdminPassword      string
	AttackForeignUser        string
	VerifyWaitSeconds        int
	KeyPoolLookbackMinutes   int
	LifecycleRequiredKeys    int
	KeyPoolRetrySeconds      int
	UpdateVerifyEnabled      bool
	UpdateVerifyTarget       float64
}

type server struct {
	mu                      sync.RWMutex
	runs                    map[string]*RunResult
	runOrder                []string
	securityRuns            map[string]*SecurityRunResult
	securityOrder           []string
	proofRuns               map[string]*ProofRunResult
	proofOrder              []string
	acceptanceEvidence      map[string]*AcceptanceEvidence
	acceptanceEvidenceOrder []string
	scenarios               map[string]Scenario
	dataDir                 string
	runsFile                string
	acceptanceEvidenceFile  string
	defaultWrkPath          string
	bashPath                string
	securityScript          string
	counter                 uint64
	cfg                     acceptanceConfig
	client                  *http.Client
}

func main() {
	wd, err := os.Getwd()
	if err != nil {
		log.Fatalf("getwd failed: %v", err)
	}

	dataDir := filepath.Join(wd, "data")
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		log.Fatalf("mkdir data failed: %v", err)
	}

	cfg := loadAcceptanceConfig()
	if cfg.GenerateInternalToken == "" {
		log.Fatal("ACCEPTANCE_INTERNAL_TOKEN or INTERNAL_TOKEN must be set; refusing to start with a public fallback token")
	}
	srv := &server{
		runs:                   make(map[string]*RunResult),
		securityRuns:           make(map[string]*SecurityRunResult),
		proofRuns:              make(map[string]*ProofRunResult),
		acceptanceEvidence:     make(map[string]*AcceptanceEvidence),
		scenarios:              defaultScenarios(cfg),
		dataDir:                dataDir,
		runsFile:               filepath.Join(dataDir, "runs.json"),
		acceptanceEvidenceFile: filepath.Join(dataDir, "acceptance-evidence.json"),
		defaultWrkPath:         detectWrkPath(wd),
		bashPath:               detectBashPath(),
		securityScript:         detectSecurityScriptPath(wd),
		cfg:                    cfg,
		client:                 &http.Client{Timeout: 30 * time.Second},
	}
	if err := srv.loadRuns(); err != nil {
		log.Printf("load runs failed: %v", err)
	}
	if err := srv.loadAcceptanceEvidence(); err != nil {
		log.Printf("load acceptance evidence failed: %v", err)
	}

	app := fiber.New()
	guard := newDemoGuard(srv)
	app.Use(guard.authorize)

	app.Get("/api/health", srv.handleHealth)
	app.Get("/api/scenarios", srv.handleScenarios)
	app.Get("/api/runs", srv.handleRuns)
	app.Get("/api/runs/:id", srv.handleRun)
	app.Post("/api/runs", srv.handleCreateRun)
	app.Get("/api/security/runs", srv.handleSecurityRuns)
	app.Post("/api/security/runs", srv.handleCreateSecurityRun)
	app.Get("/api/proof/runs", srv.handleProofRuns)
	app.Post("/api/proof/runs", srv.handleCreateProofRun)
	app.Get("/api/acceptance/criteria", srv.handleAcceptanceCriteria)
	app.Get("/api/acceptance/evidence", srv.handleAcceptanceEvidence)
	app.Post("/api/acceptance/evidence", srv.handleCreateAcceptanceEvidence)

	port := envOrDefault("PORT", "9090")
	log.Printf("kms-acceptance backend listening on :%s", port)
	log.Fatal(app.Listen(":" + port))
}

func loadAcceptanceConfig() acceptanceConfig {
	acceptanceUser := envOrDefault("ACCEPTANCE_USER", "acceptance_user")
	return acceptanceConfig{
		AbnormalRevocationURL:    envOrDefault("ACCEPTANCE_ABNORMAL_REVOCATION_URL", "http://127.0.0.1:8000/api/pqkds/internal/acceptance/abnormal-revocation/"),
		SymmetricReclamationURL:  envOrDefault("ACCEPTANCE_SYMMETRIC_RECLAMATION_URL", "http://127.0.0.1:8000/api/pqkds/internal/acceptance/symmetric-reclamation/"),
		GenerateInternalToken:    envOrDefault("ACCEPTANCE_INTERNAL_TOKEN", strings.TrimSpace(os.Getenv("INTERNAL_TOKEN"))),
		GenerateKeyPoolURL:       envOrDefault("ACCEPTANCE_GENERATE_KEY_POOL_URL", "http://127.0.0.1:9081/internal/generate/keys/recent"),
		LifecycleVerifyURL:       envOrDefault("ACCEPTANCE_LIFECYCLE_VERIFY_URL", "http://127.0.0.1:9082/internal/lifecycle/key-status"),
		LifecycleProofURL:        envOrDefault("ACCEPTANCE_LIFECYCLE_PROOF_URL", "http://127.0.0.1:9082/internal/lifecycle/batch-proof"),
		PreallocationEvidenceURL: envOrDefault("ACCEPTANCE_PREALLOCATION_EVIDENCE_URL", "http://127.0.0.1:8000/api/pqkds/internal/acceptance/preallocation-evidence/"),
		GenerateJavaBaseURL:      envOrDefault("ACCEPTANCE_GENERATE_JAVA_BASE_URL", "http://127.0.0.1:9081"),
		LifecycleJavaBaseURL:     envOrDefault("ACCEPTANCE_LIFECYCLE_JAVA_BASE_URL", "http://127.0.0.1:9082"),
		AcceptanceUser:           acceptanceUser,
		AttackUserName:           envOrDefault("ACCEPTANCE_ATTACK_USER_NAME", acceptanceUser),
		AttackUserPassword:       envOrDefault("ACCEPTANCE_ATTACK_USER_PASSWORD", ""),
		AttackAdminUserName:      envOrDefault("ACCEPTANCE_ATTACK_ADMIN_NAME", "admin"),
		AttackAdminPassword:      envOrDefault("ACCEPTANCE_ATTACK_ADMIN_PASSWORD", ""),
		AttackForeignUser:        envOrDefault("ACCEPTANCE_ATTACK_FOREIGN_USER", "admin"),
		VerifyWaitSeconds:        envOrDefaultInt("ACCEPTANCE_REVOKE_VERIFY_WAIT_SECONDS", 30),
		KeyPoolLookbackMinutes:   envOrDefaultInt("ACCEPTANCE_KEY_POOL_LOOKBACK_MINUTES", 120),
		LifecycleRequiredKeys:    envOrDefaultInt("ACCEPTANCE_LIFECYCLE_REQUIRED_KEYS", 0),
		KeyPoolRetrySeconds:      envOrDefaultInt("ACCEPTANCE_KEY_POOL_RETRY_SECONDS", 30),
		UpdateVerifyEnabled:      envOrDefaultBool("ACCEPTANCE_UPDATE_VERIFY_ENABLED", true),
		UpdateVerifyTarget:       envOrDefaultFloat("ACCEPTANCE_UPDATE_VERIFY_TARGET", 98),
	}
}

func defaultScenarios(cfg acceptanceConfig) map[string]Scenario {
	generateBaseURL := envOrDefault("ACCEPTANCE_GENERATE_BASE_URL", "http://127.0.0.1:8081")
	lifecycleBaseURL := envOrDefault("ACCEPTANCE_LIFECYCLE_BASE_URL", "http://127.0.0.1:8082")
	tokenHeader := map[string]string{
		"Content-Type":     "application/json",
		"Accept":           "application/json",
		"X-Internal-Token": cfg.GenerateInternalToken,
		// Go 入站层不再信任请求体中的 user 字段，身份一律取自该内部头。
		// 压测/验收直接调用 Go 时同样必须携带，否则会被 401 拒绝。
		"X-Kms-User": cfg.AcceptanceUser,
	}

	return map[string]Scenario{
		"symmetric-reclaim-tps": {
			ID: "symmetric-reclaim-tps", Name: "对称密钥回收速率", TargetTPS: 10000, TargetOperator: ">=",
			Method: http.MethodPost, DurationSeconds: 5, Threads: 1, Connections: 1,
			Description: "构造12000条到期SM4预分配密钥及4条对照，调用实际过期清理逻辑，按独立密钥删除数量计速。",
			Notes:       []string{"计时包含数据库过期筛选、删除及提交，不含样本生成入库、回收后快照核验、临时表清理和HTTP通信。", "使用隔离MySQL临时表测量数据库池项清理，不包含节点本地文件销毁，也不代表生产持久化吞吐。"},
		},
		"generate-tps": {
			ID:              "generate-tps",
			Name:            "密钥生成 TPS",
			TargetTPS:       100000,
			TargetOperator:  ">=",
			Method:          http.MethodPost,
			BaseURL:         generateBaseURL,
			Path:            "/generate/request/ENROLL_KEY",
			DurationSeconds: 1,
			Threads:         2,
			Connections:     340,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"user":"%s","encryt_type":"无证书非对称加密","encryt_name":"SSCL","ua":"04e5df58dcdd1d8bba99bc62b825fd1abbb8b4c2d32aa4ed79f48bb5b1dd2e14e09f5d47296df715dd748951b6e22805b0e71bfd4097e7db93cd6528cb68870f2a","key_domain":"acceptance","key_name":"acceptance-load","key_use":"性能验收","auto_update":"false"}`, cfg.AcceptanceUser),
			Description:     "并发调用SSCL密钥生成接口，以HTTP成功响应数量除以测试时长计算接口成功响应速率。",
			Notes:           []string{"本项按HTTP成功响应吞吐测量，成功数为完成请求数扣除非成功响应数。", "计时不等待异步登记、状态查询、材料摘要核验及上链确认。"},
		},
		"update-tps": {
			ID:              "update-tps",
			Name:            "密钥更新 TPS",
			TargetTPS:       5000,
			TargetOperator:  ">=",
			Method:          http.MethodPost,
			BaseURL:         lifecycleBaseURL,
			Path:            "/lifecycle/request/UPDATE_KEY",
			DurationSeconds: 5,
			Threads:         2,
			Connections:     50,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"keyId":%s,"user":"%s","keyName":"acceptance-rotate","keyUse":"性能验收","keyDomain":"acceptance","autoUpdate":"false"}`, keyIDPlaceholder, cfg.AcceptanceUser),
			MetricKind:      "update_final_rate",
			MetricTarget:    cfg.UpdateVerifyTarget,
			MetricOperator:  ">=",
			Description:     "复用已生成的 6000 把 SM2 验收密钥，每把更新一次，按版本及材料变化核验落库完成；上链异步处理。",
			Notes:           []string{"每轮固定 6000 把不同的已有 SM2 密钥，各提交一次更新；不足时明确报错。", "实际更新速率按落库完成数 / 从提交到数据库核验的耗时计算，包含排队及查询，不等待上链。"},
		},
		"revoke-tps": {
			ID:              "revoke-tps",
			Name:            "异常检测与自动回收",
			TargetTPS:       5000,
			TargetOperator:  ">=",
			Method:          http.MethodPost,
			BaseURL:         lifecycleBaseURL,
			Path:            "/lifecycle/request/REVOKE_KEY",
			DurationSeconds: 5,
			Threads:         2,
			Connections:     50,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"keyId":%s,"user":"%s"}`, keyIDPlaceholder, cfg.AcceptanceUser),
			Description:     "构造 6000 把异常公钥记录与 4 把对照密钥，调用生产异常扫描与自动回收流程，核验检测、回收及池项和会话联动。",
			Notes:           []string{"使用连接隔离的 MySQL 临时表，测试结束清理，业务数据不参与。", "速率按实际回收数 / 扫描回收耗时计算，包含检测与联动写入；不包含样本准备、清理和链上确认。", "这是隔离临时表环境测量，不代表生产负载下的持久化吞吐。"},
		},
		"revoke-rate": {
			ID:              "revoke-rate",
			Name:            "异常密钥回收率",
			TargetOperator:  ">=",
			Method:          http.MethodPost,
			BaseURL:         lifecycleBaseURL,
			Path:            "/lifecycle/request/REVOKE_KEY",
			DurationSeconds: 5,
			Threads:         2,
			Connections:     50,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"keyId":%s,"user":"%s"}`, keyIDPlaceholder, cfg.AcceptanceUser),
			MetricKind:      "abnormal_revoke_rate",
			MetricTarget:    98,
			MetricOperator:  ">=",
			Description:     "构造 6000 把异常密钥记录，按最终回收成功数 / 实际发起回收密钥数计算回收率，目标不低于 98%。",
			Notes:           []string{"使用连接隔离的 MySQL 临时表，测试结束清理，业务数据不参与。", "分母来自扫描器实际回收候选集，按密钥去重；发起后失败的密钥计入分母，未发起和4把对照单独展示。", "回收率与每秒 5000 条的速率要求独立，不按速率或固定秒数截断；所有已发起操作成功时如实显示 100%。"},
		},
	}
}

func detectWrkPath(wd string) string {
	candidates := []string{
		envOrDefault("WRK_PATH", ""),
		filepath.Join(wd, "..", "..", "kms-ops", "wrk", "wrk.exe"),
		filepath.Join(wd, "..", "..", "kms-ops", "wrk", "wrk"),
		filepath.Join(wd, "..", "kms-ops", "wrk", "wrk.exe"),
		filepath.Join(wd, "..", "kms-ops", "wrk", "wrk"),
		"wrk.exe",
		"wrk",
	}
	for _, candidate := range candidates {
		if path, ok := resolveExecutable(candidate); ok {
			return path
		}
	}
	return ""
}

func resolveExecutable(candidate string) (string, bool) {
	candidate = strings.TrimSpace(candidate)
	if candidate == "" {
		return "", false
	}
	if path, err := exec.LookPath(candidate); err == nil {
		return path, true
	}
	if isExecutableFile(candidate) {
		return candidate, true
	}
	return "", false
}

func isExecutableFile(path string) bool {
	info, err := os.Stat(path)
	if err != nil || info.IsDir() {
		return false
	}
	return info.Mode().IsRegular() && info.Mode().Perm()&0o111 != 0
}

func detectBashPath() string {
	if path, err := exec.LookPath("bash"); err == nil {
		return path
	}
	if path, err := exec.LookPath("sh"); err == nil {
		return path
	}
	return ""
}

func detectSecurityScriptPath(wd string) string {
	candidates := []string{
		filepath.Join(wd, "..", "..", "security", "security_test.sh"),
		filepath.Join(wd, "..", "security", "security_test.sh"),
		filepath.Join(wd, "security", "security_test.sh"),
	}
	for _, candidate := range candidates {
		if fileExists(candidate) {
			return candidate
		}
	}
	return ""
}

func (s *server) handleHealth(c *fiber.Ctx) error {
	wrkPath, wrkAvailable := resolveExecutable(s.defaultWrkPath)
	return c.JSON(HealthResponse{
		Status:             "ok",
		Service:            "kms-acceptance-backend",
		WrkAvailable:       wrkAvailable,
		WrkPath:            wrkPath,
		SecurityScriptPath: "system_security.go",
		SecurityExecutable: "native-http-probes",
		SecurityAvailable:  len(systemSecurityCases) > 0,
		DataDir:            s.dataDir,
		Now:                time.Now().Format(time.RFC3339),
		AcceptanceUser:     s.cfg.AcceptanceUser,
		GenerateKeyPoolURL: s.cfg.GenerateKeyPoolURL,
		LifecycleVerifyURL: s.cfg.LifecycleVerifyURL,
		LifecycleProofURL:  s.cfg.LifecycleProofURL,
	})
}

func (s *server) handleScenarios(c *fiber.Ctx) error {
	list := make([]Scenario, 0, len(s.scenarios))
	for _, scenario := range s.scenarios {
		list = append(list, scenario)
	}
	sort.Slice(list, func(i, j int) bool { return list[i].ID < list[j].ID })
	return c.JSON(fiber.Map{"data": list})
}

func acceptanceCriteria() []AcceptanceCriterion {
	return []AcceptanceCriterion{
		{ID: "symmetric-reclaim", Category: "performance", Title: "对称密钥回收速率", Requirement: "到期SM4对称密钥回收 ≥ 10000 条/秒", Kind: "scenario", Target: 10000, Operator: ">=", Unit: "条/秒", ScenarioID: "symmetric-reclaim-tps", ExecutionScope: "admin", EvidenceSource: symmetricSource},
		{ID: "certless-generation", Category: "performance", Title: "密钥生成接口成功响应速率", Requirement: "HTTP成功响应速率每秒不少于100000次", Kind: "scenario", Target: 100000, Operator: ">=", Unit: "次每秒", ScenarioID: "generate-tps", ExecutionScope: "admin", EvidenceSource: "SSCL生成接口HTTP成功响应统计", Notes: []string{"HTTP成功响应数除以测试时长，不含异步登记及后续核验时间。"}},
		{ID: "preallocation", Category: "performance", Title: "预分配密钥速率", Requirement: "节点侧本机封装吞吐 > 50 条/秒", Kind: "evidence", Target: 50, Operator: ">", Unit: "条/秒", ExecutionScope: "node", EvidenceSource: "独立节点侧预分配验收流程（需单独发起）", Notes: []string{"日常预分配不作为验收样本，也不自动回传量化结果。管理端未发起任务时状态为未执行。"}},
		{ID: "key-update", Category: "performance", Title: "密钥更新速率", Requirement: "成功更新 TPS ≥ 5000 条/秒", Kind: "scenario", Target: 5000, Operator: ">=", Unit: "TPS", ScenarioID: "update-tps", ExecutionScope: "admin", EvidenceSource: "kms-updatedel / 固定 6000 条版本变化核验"},
		{ID: "abnormal-revoke", Category: "performance", Title: "异常密钥回收速率", Requirement: "实际异常自动回收 ≥ 5000 条/秒", Kind: "scenario", Target: 5000, Operator: ">=", Unit: "TPS", ScenarioID: "revoke-tps", ExecutionScope: "admin", EvidenceSource: "node auto-revoke / isolated MySQL", Notes: []string{"先写入异常样本，再检测、自动回收并验证正常对照与依赖失效。"}},
		{ID: "revoke-rate", Category: "performance", Title: "异常密钥回收率", Requirement: "异常密钥回收率 ≥ 98%", Kind: "scenario", Target: 98, Operator: ">=", Unit: "%", ScenarioID: "revoke-rate", ExecutionScope: "admin", EvidenceSource: "node auto-revoke / isolated MySQL 状态快照"},
		{ID: "generation-attacks", Category: "security", Title: "密钥生成协议校验", Requirement: "签发入口非法请求明确拒绝", Kind: "security-suite", Target: 3, Operator: ">=", Unit: "类", CaseIDs: []string{"generation-identity-injection", "generation-unknown-algorithm", "generation-malformed-json", "generation-invalid-version"}, ExecutionScope: "admin", EvidenceSource: "system_security.go / 实际 Demo 网关"},
		{ID: "quantum-attacks", Category: "security", Title: "量子攻击仿真与参数评估", Requirement: "系统能够抵御量子攻击种类不少于3种", Kind: "security-suite", Target: 3, Operator: ">=", Unit: "种", CaseIDs: []string{"quantum-lwe-usvp", "quantum-lwe-bdd", "quantum-lwe-dual"}, ExecutionScope: "admin", EvidenceSource: "弱参数Grover电路 + lattice-estimator量子筛法成本模型 + 部署原生KYBER业务对照", Notes: []string{"三项为不同格攻击成本模型，共用弱参数电路正向对照。评估完成不自动判定任务书抗攻击指标通过。"}},
		{ID: "network-attacks", Category: "security", Title: "网络攻击", Requirement: "会话与权限边界请求明确拒绝", Kind: "security-suite", Target: 5, Operator: ">=", Unit: "类", CaseIDs: []string{"network-session-forgery", "network-csrf", "network-stale-revision", "network-role-isolation", "network-origin", "network-missing-session"}, ExecutionScope: "admin", EvidenceSource: "system_security.go / 实际会话与权限接口"},
	}
}

func (s *server) handleAcceptanceCriteria(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{"data": acceptanceCriteria()})
}

func (s *server) handleAcceptanceEvidence(c *fiber.Ctx) error {
	remote, err := s.fetchPreallocationEvidence(c.Context())
	if err != nil {
		// 节点证据服务可能暂时未部署。保留本地历史记录并显式标记来源不可用，
		// 不把管理端看板整体伪装成空数据或直接打成 503。
		log.Printf("preallocation evidence source unavailable: %v", err)
		remote = nil
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	list := make([]*AcceptanceEvidence, 0, len(remote)+len(s.acceptanceEvidenceOrder))
	for index := range remote {
		item := remote[index]
		list = append(list, &item)
	}
	for i := len(s.acceptanceEvidenceOrder) - 1; i >= 0; i-- {
		list = append(list, s.acceptanceEvidence[s.acceptanceEvidenceOrder[i]])
	}
	return c.JSON(fiber.Map{"data": list})
}

func (s *server) fetchPreallocationEvidence(parent context.Context) ([]AcceptanceEvidence, error) {
	url := strings.TrimSpace(s.cfg.PreallocationEvidenceURL)
	if url == "" {
		return nil, errors.New("ACCEPTANCE_PREALLOCATION_EVIDENCE_URL 未配置")
	}
	ctx, cancel := context.WithTimeout(parent, 5*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	var envelope acceptanceEvidenceEnvelope
	if err := json.NewDecoder(io.LimitReader(resp.Body, 2<<20)).Decode(&envelope); err != nil {
		return nil, err
	}
	if envelope.Code != 200 {
		return nil, fmt.Errorf("证据接口返回 code=%d", envelope.Code)
	}
	return envelope.Data, nil
}

func (s *server) handleCreateAcceptanceEvidence(c *fiber.Ctx) error {
	var req AcceptanceEvidenceRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "invalid request body"})
	}
	criterion, ok := acceptanceCriterionByID(req.CriterionID)
	if !ok || (criterion.Kind != "evidence" && criterion.Kind != "security-suite") {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "criterion does not accept manual evidence"})
	}
	if req.Value < 0 || strings.TrimSpace(req.Evidence) == "" {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "value and evidence are required"})
	}
	measuredAt := strings.TrimSpace(req.MeasuredAt)
	if measuredAt == "" {
		measuredAt = time.Now().Format(time.RFC3339)
	}
	item := &AcceptanceEvidence{ID: s.nextID(), CriterionID: criterion.ID, Value: req.Value, Unit: criterion.Unit, Operator: criterion.Operator, Target: criterion.Target, Passed: compareThreshold(req.Value, criterion.Operator, criterion.Target), Evidence: strings.TrimSpace(req.Evidence), MeasuredAt: measuredAt, RecordedAt: time.Now().Format(time.RFC3339)}
	s.mu.Lock()
	s.acceptanceEvidence[item.ID] = item
	s.acceptanceEvidenceOrder = append(s.acceptanceEvidenceOrder, item.ID)
	err := s.persistAcceptanceEvidenceLocked()
	s.mu.Unlock()
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"message": "persist acceptance evidence failed"})
	}
	return c.JSON(item)
}

func acceptanceCriterionByID(id string) (AcceptanceCriterion, bool) {
	for _, item := range acceptanceCriteria() {
		if item.ID == id {
			return item, true
		}
	}
	return AcceptanceCriterion{}, false
}

func compareThreshold(value float64, operator string, target float64) bool {
	if operator == ">" {
		return value > target
	}
	return value >= target
}

func (s *server) handleRuns(c *fiber.Ctx) error {
	s.mu.RLock()
	defer s.mu.RUnlock()

	list := make([]*RunResult, 0, len(s.runOrder))
	for i := len(s.runOrder) - 1; i >= 0; i-- {
		id := s.runOrder[i]
		list = append(list, s.runs[id])
	}
	return c.JSON(fiber.Map{"data": list})
}

func (s *server) handleRun(c *fiber.Ctx) error {
	id := c.Params("id")
	s.mu.RLock()
	run, ok := s.runs[id]
	s.mu.RUnlock()
	if !ok {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"message": "run not found"})
	}
	return c.JSON(run)
}

func (s *server) handleSecurityRuns(c *fiber.Ctx) error {
	s.mu.RLock()
	defer s.mu.RUnlock()

	list := make([]*SecurityRunResult, 0, len(s.securityOrder))
	for i := len(s.securityOrder) - 1; i >= 0; i-- {
		id := s.securityOrder[i]
		list = append(list, s.securityRuns[id])
	}
	return c.JSON(fiber.Map{"data": list})
}

func (s *server) handleCreateSecurityRun(c *fiber.Ctx) error {
	var req SecurityRunRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "invalid request body"})
	}
	caseID := strings.TrimSpace(req.CaseID)
	if caseID == "" {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "caseId is required"})
	}
	if !systemSecurityCases[caseID] {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "旧版或未知安全用例不适用当前系统"})
	}

	run := &SecurityRunResult{
		ID:        s.nextID(),
		CaseID:    caseID,
		Status:    "running",
		StartedAt: time.Now().Format(time.RFC3339),
	}
	s.storeSecurityRun(run)

	result := s.executeSecurityRun(caseID)
	run.Status = result.Status
	run.Verdict = result.Verdict
	run.Passed = result.Passed
	run.FinishedAt = time.Now().Format(time.RFC3339)
	run.Summary = result.Summary
	run.Error = result.Error
	run.Notes = append([]string{}, result.Notes...)
	run.Requests = append([]SecurityRequestTrace{}, result.Requests...)
	run.ProbeSteps = append([]SecurityProbeStep{}, result.ProbeSteps...)
	run.RawOutput = result.RawOutput
	run.ExpectedCode = result.ExpectedCode
	run.ActualCode = result.ActualCode
	run.LegalControlPassed = result.LegalControlPassed
	run.EvidenceVersion = result.EvidenceVersion
	run.TestInput = result.TestInput
	run.ValidationRule = result.ValidationRule
	run.ExpectedReason = result.ExpectedReason
	run.ActualReason = result.ActualReason
	run.ReasonMatched = result.ReasonMatched
	run.ProtocolPassed = result.ProtocolPassed
	run.AlgorithmEvidence = result.AlgorithmEvidence
	run.QuantumEvidence = result.QuantumEvidence
	s.storeSecurityRun(run)

	if run.Status == "error" {
		return c.Status(http.StatusBadGateway).JSON(run)
	}
	return c.JSON(run)
}

func (s *server) handleProofRuns(c *fiber.Ctx) error {
	s.mu.RLock()
	defer s.mu.RUnlock()

	list := make([]*ProofRunResult, 0, len(s.proofOrder))
	for i := len(s.proofOrder) - 1; i >= 0; i-- {
		id := s.proofOrder[i]
		list = append(list, s.proofRuns[id])
	}
	return c.JSON(fiber.Map{"data": list})
}

func (s *server) handleCreateProofRun(c *fiber.Ctx) error {
	var req ProofRunRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "invalid request body"})
	}
	if req.BatchSize <= 0 {
		req.BatchSize = 5
	}
	if req.BatchSize > 32 {
		req.BatchSize = 32
	}
	if req.TreeFanout <= 0 {
		req.TreeFanout = 4
	}
	if strings.TrimSpace(req.ProofMode) == "" {
		req.ProofMode = "semi_honest"
	}
	if strings.TrimSpace(req.LifecycleBaseURL) == "" {
		req.LifecycleBaseURL = s.scenarios["update-tps"].BaseURL
	}

	run := &ProofRunResult{
		ID:         s.nextID(),
		Status:     "running",
		StartedAt:  time.Now().Format(time.RFC3339),
		BatchSize:  req.BatchSize,
		TreeFanout: req.TreeFanout,
		ProofMode:  req.ProofMode,
	}
	s.storeProofRun(run)

	result := s.executeProofRun(req)
	run.Status = result.Status
	run.Passed = result.Passed
	run.FinishedAt = time.Now().Format(time.RFC3339)
	run.BatchID = result.BatchID
	run.Summary = result.Summary
	run.TreeCheck = result.TreeCheck
	run.ProofCheck = result.ProofCheck
	run.Records = append([]ProofRecord{}, result.Records...)
	run.Notes = append([]string{}, result.Notes...)
	run.Error = result.Error
	s.storeProofRun(run)

	if run.Status == "error" {
		return c.Status(http.StatusBadGateway).JSON(run)
	}
	return c.JSON(run)
}

func (s *server) handleCreateRun(c *fiber.Ctx) error {
	var req RunRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "invalid request body"})
	}

	scenario, ok := s.scenarios[req.ScenarioID]
	if !ok {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "unknown scenario"})
	}

	resolved := s.resolveScenario(scenario, req)
	if resolved.BaseURL == "" || resolved.Path == "" {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": "baseUrl and path are required"})
	}

	prepared, notes, err := s.prepareScenario(resolved)
	if err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"message": err.Error()})
	}

	wrkPath := strings.TrimSpace(req.WrkPath)
	if wrkPath == "" {
		wrkPath = s.defaultWrkPath
	}
	resolvedWrkPath, ok := resolveExecutable(wrkPath)
	if !ok && prepared.ID != "update-tps" && !abnormalScenario(prepared.ID) && !symmetricScenario(prepared.ID) {
		return c.Status(http.StatusServiceUnavailable).JSON(fiber.Map{"message": "wrk not found or not executable, set WRK_PATH or provide wrkPath"})
	}
	wrkPath = resolvedWrkPath

	runID := s.nextID()
	run := &RunResult{
		ID:         runID,
		ScenarioID: prepared.ID,
		Scenario:   prepared.Name,
		Status:     "running",
		StartedAt:  time.Now().Format(time.RFC3339),
		TargetTPS:  prepared.TargetTPS,
		Notes:      append(append([]string{}, prepared.Notes...), notes...),
	}
	s.storeRun(run)

	var updateAudit *lifecycleArchive
	var updateRows []lifecycleRow
	if prepared.ID == "update-tps" {
		updateAudit, updateRows, err = s.beginLifecycleAudit(context.Background(), prepared, *run, "standalone", 0)
		if err == nil && (updateAudit == nil || updateAudit.Batch.Eligible != fixedUpdateCount || updateAudit.Batch.Excluded != 0) {
			err = fmt.Errorf("本轮有效密钥不足 6000 把")
		}
		if err != nil {
			run.Status, run.Error = "failed", "无法记录更新前的密钥状态"
			s.storeRun(run)
			return c.Status(http.StatusBadGateway).JSON(run)
		}
	}
	result := s.executeRun(context.Background(), wrkPath, prepared)
	if result.Symmetric != nil {
		archive, rows := symmetricAudit(*run, result.Symmetric, "standalone", 0)
		archive.Batch.Status, archive.Batch.FinishedAt = result.Status, time.Now().Format(time.RFC3339)
		if err := s.saveLifecycleAudit(*archive, rows); err != nil {
			result.Status, result.Error = "failed", "对称密钥回收证据归档失败"
		}
		result.Symmetric.Rows = nil
	}
	if updateAudit != nil {
		if err := s.finishLifecycleAudit(context.Background(), updateAudit, updateRows, result); err != nil {
			result.Status, result.Error = "failed", "更新状态核验归档失败"
		}
		result = applyLifecycleAuditResult(prepared, updateAudit, result)
		updateAudit.Batch.Status, updateAudit.Batch.FinishedAt = result.Status, time.Now().Format(time.RFC3339)
		if err := s.saveLifecycleAudit(*updateAudit, updateRows); err != nil {
			result.Status, result.Error = "failed", "更新测量归档失败"
		}
	}
	run.Status = result.Status
	run.FinishedAt = time.Now().Format(time.RFC3339)
	run.PassedTPS = result.PassedTPS
	run.Summary = result.Summary
	run.WrkCommand = result.WrkCommand
	run.Error = result.Error
	run.Abnormal = result.Abnormal
	run.FixedUpdate = result.FixedUpdate
	run.Symmetric = result.Symmetric
	run.Generation = result.Generation
	if run.Abnormal != nil {
		run.Abnormal.Rows = nil
	}
	run.MetricCheck = result.MetricCheck
	if len(result.Notes) > 0 {
		run.Notes = append(run.Notes, result.Notes...)
	}
	s.storeRun(run)

	if result.Status == "failed" {
		return c.Status(http.StatusBadGateway).JSON(run)
	}
	return c.JSON(run)
}

func (s *server) prepareScenario(base Scenario) (Scenario, []string, error) {
	return s.prepareScenarioContext(context.Background(), base)
}

func (s *server) prepareScenarioContext(ctx context.Context, base Scenario) (Scenario, []string, error) {
	prepared := base
	var notes []string
	if abnormalScenario(base.ID) || symmetricScenario(base.ID) {
		return prepared, notes, nil
	}

	if !strings.Contains(prepared.BodyTemplate, keyIDPlaceholder) {
		return prepared, notes, nil
	}

	requiredKeys := s.cfg.LifecycleRequiredKeys
	if base.ID == "update-tps" {
		requiredKeys = fixedUpdateCount
	} else if requiredKeys <= 0 {
		requiredKeys = int(prepared.TargetTPS * float64(prepared.DurationSeconds))
	}
	if requiredKeys <= 0 {
		requiredKeys = prepared.Connections
	}

	createdAfter := base.GeneratedAfter
	if base.ID == "update-tps" {
		// Generation throughput uses SSCL. Its timestamp does not identify the
		// separately prepared SM2 rotation pool, which is reused on every run.
		createdAfter = time.Time{}
		prepared.SourceRunID = ""
	}
	if createdAfter.IsZero() && base.ID != "update-tps" {
		createdAfter = s.latestGenerateStartedAt()
	}
	if createdAfter.IsZero() {
		if base.ID == "update-tps" {
			notes = append(notes, "复用验收用户已生成的最新 6000 把有效验收密钥，不重新生成。")
		} else {
			createdAfter = time.Now().Add(-time.Duration(s.cfg.KeyPoolLookbackMinutes) * time.Minute)
			notes = append(notes, fmt.Sprintf("未找到最近一次生成压测记录，回退到最近 %d 分钟生成数据取 key 池。", s.cfg.KeyPoolLookbackMinutes))
		}
	} else {
		notes = append(notes, fmt.Sprintf("复用最近一次生成压测开始时间 %s 之后的 key 池。", createdAfter.Format(time.RFC3339)))
	}

	algorithm := ""
	if base.ID == "update-tps" {
		algorithm = "SM2"
		notes = append(notes, "使用 SM2 随机刷新 KGC 份额，落库完成即计更新，上链异步处理。")
	}
	keyIDs, err := s.fetchGeneratedKeyIDsContext(ctx, requiredKeys, createdAfter, algorithm, base.ID == "update-tps")
	if err != nil {
		return prepared, notes, err
	}
	prepared.PreparedKeyIDs = keyIDs
	if base.ID == "update-tps" {
		notes = append(notes, "已装载 6000 把不同密钥，本轮每把更新一次。")
	} else {
		notes = append(notes, fmt.Sprintf("已装载 %d 个 keyId 作为 wrk 轮换池。", len(keyIDs)))
	}
	return prepared, notes, nil
}

func (s *server) latestGenerateStartedAt() time.Time {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for i := len(s.runOrder) - 1; i >= 0; i-- {
		run := s.runs[s.runOrder[i]]
		if run != nil && run.ScenarioID == "generate-tps" {
			if ts, err := time.Parse(time.RFC3339, run.StartedAt); err == nil {
				return ts
			}
		}
	}
	return time.Time{}
}

func (s *server) fetchGeneratedKeyIDs(limit int, createdAfter time.Time, encrytName string) ([]int64, error) {
	return s.fetchGeneratedKeyIDsContext(context.Background(), limit, createdAfter, encrytName, false)
}

func (s *server) fetchGeneratedKeyIDsContext(ctx context.Context, limit int, createdAfter time.Time, encrytName string, activeOnly bool) ([]int64, error) {
	if limit <= 0 {
		return nil, fmt.Errorf("invalid key pool size")
	}

	deadline := time.Now().Add(time.Duration(s.cfg.KeyPoolRetrySeconds) * time.Second)
	if s.cfg.KeyPoolRetrySeconds <= 0 {
		deadline = time.Now()
	}

	var lastErr error
	for {
		keyIDs, err := s.fetchGeneratedKeyIDsOnce(ctx, limit, createdAfter, encrytName, activeOnly)
		if err == nil {
			return keyIDs, nil
		}
		lastErr = err
		if ctx.Err() != nil || time.Now().After(deadline) {
			return nil, lastErr
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
}

func (s *server) fetchGeneratedKeyIDsOnce(ctx context.Context, limit int, createdAfter time.Time, encrytName string, activeOnly bool) ([]int64, error) {
	endpoint, err := url.Parse(s.cfg.GenerateKeyPoolURL)
	if err != nil {
		return nil, fmt.Errorf("invalid generate key pool url: %w", err)
	}
	query := endpoint.Query()
	query.Set("userName", s.cfg.AcceptanceUser)
	query.Set("limit", strconv.Itoa(limit))
	if activeOnly {
		query.Set("activeOnly", "true")
	}
	if !createdAfter.IsZero() {
		query.Set("createdAfter", createdAfter.Format(time.RFC3339))
	}
	if strings.TrimSpace(encrytName) != "" {
		query.Set("encrytName", strings.TrimSpace(encrytName))
	}
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("load generated key pool failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= http.StatusBadRequest {
		return nil, fmt.Errorf("generate key pool api returned %d", resp.StatusCode)
	}

	var payload internalGenerateResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode generated key pool failed: %w", err)
	}
	if len(payload.Data) < limit {
		return nil, fmt.Errorf("generated key pool is not enough: need %d keys, got %d", limit, len(payload.Data))
	}

	keyIDs := make([]int64, 0, limit)
	seen := make(map[int64]struct{}, limit)
	for _, item := range payload.Data {
		if activeOnly && (item.UserName != s.cfg.AcceptanceUser || item.Status != "0" || item.KeyDomain != "acceptance") {
			return nil, fmt.Errorf("generated key pool contains an invalid or non-acceptance key")
		}
		if item.KeyID == 0 {
			continue
		}
		if _, exists := seen[item.KeyID]; exists {
			continue
		}
		seen[item.KeyID] = struct{}{}
		keyIDs = append(keyIDs, item.KeyID)
		if len(keyIDs) >= limit {
			break
		}
	}
	if len(keyIDs) < limit {
		return nil, fmt.Errorf("generated key pool contains only %d unique keys, need %d", len(keyIDs), limit)
	}
	return keyIDs, nil
}

func (s *server) executeRun(parentCtx context.Context, wrkPath string, scenario Scenario) RunResult {
	if symmetricScenario(scenario.ID) {
		return s.executeSymmetricReclamation(parentCtx, scenario)
	}
	if scenario.ID == "update-tps" {
		return s.executeFixedUpdate(parentCtx, scenario)
	}
	if abnormalScenario(scenario.ID) {
		return s.executeAbnormalRevocation(parentCtx, scenario)
	}
	runDir := filepath.Join(s.dataDir, strings.ReplaceAll(s.nextID(), ":", "-"))
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return RunResult{Status: "failed", Error: "create run temp dir failed: " + err.Error()}
	}
	defer os.RemoveAll(runDir)

	luaFile := filepath.Join(runDir, "request.lua")
	args := []string{
		"-t", strconv.Itoa(scenario.Threads),
		"-c", strconv.Itoa(scenario.Connections),
		"-d", fmt.Sprintf("%ds", scenario.DurationSeconds),
		"--latency",
	}
	for key, value := range scenario.Headers {
		args = append(args, "-H", fmt.Sprintf("%s: %s", key, value))
	}
	if strings.EqualFold(scenario.Method, http.MethodPost) || strings.EqualFold(scenario.Method, http.MethodPut) || strings.EqualFold(scenario.Method, http.MethodDelete) {
		args = append(args, "-s", luaFile)
	}

	url := strings.TrimRight(scenario.BaseURL, "/") + scenario.Path
	if err := os.WriteFile(luaFile, []byte(buildLuaScript(scenario.Method, scenario.Path, scenario.BodyTemplate, scenario.Headers, scenario.PreparedKeyIDs)), 0o644); err != nil {
		return RunResult{Status: "failed", Error: "write lua script failed: " + err.Error()}
	}
	args = append(args, url)

	ctx, cancel := context.WithTimeout(parentCtx, time.Duration(scenario.DurationSeconds+30)*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, wrkPath, args...)

	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stdout

	if err := cmd.Run(); err != nil {
		return RunResult{
			Status:     "failed",
			Error:      "wrk execution failed: " + err.Error(),
			WrkCommand: append([]string{wrkPath}, args...),
			Summary:    RunSummary{RawOutput: stdout.String()},
		}
	}

	summary := parseWrkOutput(stdout.String())
	// Requests/sec includes non-2xx responses. The task-book metric is the
	// throughput of successfully accepted requests, so threshold decisions must
	// use the successful rate and retain raw request rate only for diagnostics.
	if scenario.DurationSeconds > 0 {
		// wrk's completed request count excludes socket failures. Subtract only
		// non-2xx responses here; subtracting ErrorCount would count socket
		// failures twice and under-report successful throughput.
		successful := summary.TotalRequests - summary.Non2xxResponses
		if successful < 0 {
			successful = 0
		}
		summary.SuccessfulRequestsPerSec = float64(successful) / float64(scenario.DurationSeconds)
	}
	passedTPS := compareThreshold(summary.SuccessfulRequestsPerSec, scenario.TargetOperator, scenario.TargetTPS)
	metricCheck := s.collectMetricCheck(scenario)
	status := "passed"
	if !passedTPS || (metricCheck.Enforced && (!metricCheck.Collected || !metricCheck.Passed)) {
		status = "failed_threshold"
	}

	result := RunResult{
		Status:      status,
		PassedTPS:   passedTPS,
		WrkCommand:  append([]string{wrkPath}, args...),
		Summary:     summary,
		MetricCheck: metricCheck,
	}
	if len(scenario.PreparedKeyIDs) > 0 {
		result.Notes = append(result.Notes, fmt.Sprintf("本次 wrk 轮换使用 %d 个 keyId。", len(scenario.PreparedKeyIDs)))
	}
	return result
}

func buildLuaScript(method, path, body string, headers map[string]string, keyIDs []int64) string {
	var headerLines []string
	for key, value := range headers {
		headerLines = append(headerLines, fmt.Sprintf("wrk.headers[%q] = %q", key, value))
	}
	sort.Strings(headerLines)
	base := fmt.Sprintf("wrk.method = %q\n%s\n", method, strings.Join(headerLines, "\n"))
	if len(keyIDs) == 0 || !strings.Contains(body, keyIDPlaceholder) {
		return base + fmt.Sprintf("wrk.body = %q\nfunction request()\n  return wrk.format(%q, %q, wrk.headers, wrk.body)\nend\n", body, method, path)
	}

	var keys []string
	for _, keyID := range keyIDs {
		keys = append(keys, strconv.FormatInt(keyID, 10))
	}
	return base + fmt.Sprintf("local key_ids = {%s}\nlocal idx = 1\nlocal body_template = [=[%s]=]\nfunction request()\n  local current = key_ids[idx]\n  idx = idx + 1\n  if idx > #key_ids then\n    idx = 1\n  end\n  local req_body = string.gsub(body_template, %q, tostring(current), 1)\n  return wrk.format(%q, %q, wrk.headers, req_body)\nend\n", strings.Join(keys, ","), body, keyIDPlaceholder, method, path)
}

func parseWrkOutput(output string) RunSummary {
	summary := RunSummary{RawOutput: output}
	non2xx := int64(0)
	socketErrors := int64(0)
	for _, line := range strings.Split(output, "\n") {
		trimmed := strings.TrimSpace(line)
		switch {
		case strings.HasPrefix(trimmed, "Latency"):
			fields := strings.Fields(trimmed)
			if len(fields) >= 2 {
				summary.AvgLatencyMs = parseDurationToMs(fields[1])
			}
		case strings.HasPrefix(trimmed, "Requests/sec:"):
			summary.RequestsPerSec = parseFloat(lastField(trimmed))
		case strings.HasPrefix(trimmed, "Transfer/sec:"):
			summary.TransferPerSec = lastField(trimmed)
		case strings.Contains(trimmed, "requests in") && strings.Contains(trimmed, "read"):
			matches := regexp.MustCompile(`([0-9]+) requests in .*?, ([^ ]+) read`).FindStringSubmatch(trimmed)
			if len(matches) == 3 {
				summary.TotalRequests = parseInt64(matches[1])
				summary.ReadBytes = matches[2]
			}
		case strings.HasPrefix(trimmed, "Socket errors:"):
			matches := regexp.MustCompile(`connect ([0-9]+), read ([0-9]+), write ([0-9]+), timeout ([0-9]+)`).FindStringSubmatch(trimmed)
			if len(matches) == 5 {
				socketErrors = parseInt64(matches[1]) + parseInt64(matches[2]) + parseInt64(matches[3]) + parseInt64(matches[4])
			}
		case strings.HasPrefix(trimmed, "Non-2xx or 3xx responses:"):
			non2xx = parseInt64(lastField(trimmed))
		}
	}
	summary.P99LatencyMs = parseP99Latency(output)
	summary.SocketErrors = socketErrors
	summary.Non2xxResponses = non2xx
	summary.ErrorCount = socketErrors + non2xx
	totalAttempts := summary.TotalRequests + socketErrors
	successful := summary.TotalRequests - summary.Non2xxResponses
	if totalAttempts > 0 && successful >= 0 {
		summary.SuccessRate = float64(successful) / float64(totalAttempts) * 100
	}
	return summary
}

func parseP99Latency(output string) float64 {
	matcher := regexp.MustCompile(`99%\s+([0-9.]+[a-z]+)`)
	if match := matcher.FindStringSubmatch(output); len(match) == 2 {
		return parseDurationToMs(match[1])
	}
	return 0
}

func (s *server) collectMetricCheck(scenario Scenario) MetricCheck {
	if scenario.MetricKind != "revoke_final_rate" && scenario.MetricKind != "update_final_rate" {
		return MetricCheck{}
	}
	if scenario.MetricKind == "update_final_rate" && !s.cfg.UpdateVerifyEnabled {
		return MetricCheck{Kind: scenario.MetricKind, Target: scenario.MetricTarget, Operator: scenario.MetricOperator, Source: s.cfg.LifecycleVerifyURL, Message: "update final-state verification disabled by ACCEPTANCE_UPDATE_VERIFY_ENABLED=false"}
	}
	if len(scenario.PreparedKeyIDs) == 0 {
		return MetricCheck{Kind: scenario.MetricKind, Target: scenario.MetricTarget, Operator: scenario.MetricOperator, Enforced: true, Message: "no key ids prepared", Source: s.cfg.LifecycleVerifyURL}
	}

	verified, err := s.waitLifecycleKeys(scenario.PreparedKeyIDs, scenario.MetricKind)
	if err != nil {
		return MetricCheck{Kind: scenario.MetricKind, Target: scenario.MetricTarget, Operator: scenario.MetricOperator, Enforced: true, Source: s.cfg.LifecycleVerifyURL, Message: err.Error()}
	}
	value := float64(verified) / float64(len(scenario.PreparedKeyIDs)) * 100
	return MetricCheck{
		Kind:       scenario.MetricKind,
		Value:      value,
		Target:     scenario.MetricTarget,
		Operator:   scenario.MetricOperator,
		Passed:     compareThreshold(value, scenario.MetricOperator, scenario.MetricTarget),
		Source:     s.cfg.LifecycleVerifyURL,
		Collected:  true,
		Enforced:   true,
		ReportedAt: time.Now().Format(time.RFC3339),
		Message:    fmt.Sprintf("最终状态核验通过 %d/%d", verified, len(scenario.PreparedKeyIDs)),
	}
}

func (s *server) waitLifecycleKeys(keyIDs []int64, kind string) (int, error) {
	deadline := time.Now().Add(time.Duration(s.cfg.VerifyWaitSeconds) * time.Second)
	if s.cfg.VerifyWaitSeconds <= 0 {
		deadline = time.Now()
	}

	var (
		latest  int
		lastErr error
	)
	for {
		verified, err := s.verifyLifecycleKeysOnce(keyIDs, kind)
		if err == nil {
			latest = verified
			if verified >= len(keyIDs) || time.Now().After(deadline) {
				return verified, nil
			}
		} else {
			lastErr = err
			if time.Now().After(deadline) {
				return latest, lastErr
			}
		}
		time.Sleep(2 * time.Second)
	}
}

func (s *server) verifyLifecycleKeysOnce(keyIDs []int64, kind string) (int, error) {
	if len(keyIDs) == 0 {
		return 0, nil
	}
	verified := 0
	for start := 0; start < len(keyIDs); start += 200 {
		end := start + 200
		if end > len(keyIDs) {
			end = len(keyIDs)
		}
		items, err := s.fetchLifecycleStatuses(keyIDs[start:end])
		if err != nil {
			return verified, err
		}
		for _, item := range items {
			if item.Exists && ((kind == "revoke_final_rate" && item.Status == "3") || (kind == "update_final_rate" && item.ChainStatus == "1")) {
				verified++
			}
		}
	}
	return verified, nil
}

func (s *server) fetchLifecycleStatuses(keyIDs []int64) ([]internalVerifyRecord, error) {
	return s.fetchLifecycleStatusesContext(context.Background(), keyIDs)
}

func (s *server) fetchLifecycleStatusesContext(ctx context.Context, keyIDs []int64) ([]internalVerifyRecord, error) {
	endpoint, err := url.Parse(s.cfg.LifecycleVerifyURL)
	if err != nil {
		return nil, fmt.Errorf("invalid lifecycle verify url: %w", err)
	}
	query := endpoint.Query()
	for _, keyID := range keyIDs {
		query.Add("keyIds", strconv.FormatInt(keyID, 10))
	}
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("query lifecycle status failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= http.StatusBadRequest {
		return nil, fmt.Errorf("lifecycle verify api returned %d", resp.StatusCode)
	}

	var payload internalVerifyResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode lifecycle verify payload failed: %w", err)
	}
	return payload.Data, nil
}

func (s *server) executeProofRun(req ProofRunRequest) ProofRunResult {
	keyIDs, err := s.fetchGeneratedKeyIDs(req.BatchSize, time.Now().Add(-time.Duration(s.cfg.KeyPoolLookbackMinutes)*time.Minute), "")
	if err != nil {
		return ProofRunResult{Status: "error", Error: "load visual test key pool failed: " + err.Error()}
	}

	batchResp, err := s.submitBatchUpdate(req, keyIDs)
	if err != nil {
		return ProofRunResult{Status: "error", Error: err.Error()}
	}
	result := ProofRunResult{
		BatchID:    batchResp.BatchID,
		BatchSize:  req.BatchSize,
		TreeFanout: req.TreeFanout,
		ProofMode:  req.ProofMode,
		Notes: []string{
			fmt.Sprintf("selected %d generated keys for visual proof test", len(keyIDs)),
			fmt.Sprintf("batch update accepted %d/%d, duplicates=%d", batchResp.Accepted, batchResp.Total, batchResp.Duplicate),
		},
	}
	if batchResp.BatchID == "" {
		result.Status = "error"
		result.Error = "batch update did not return batch_id"
		return result
	}

	proof, err := s.waitBatchProof(batchResp.BatchID, batchResp.Accepted)
	if err != nil {
		result.Status = "error"
		result.Error = err.Error()
		return result
	}
	result.Summary = proof.Summary
	result.Records = proof.Data
	result.TreeCheck = buildTreeVisualCheck(proof.Summary, proof.Data)
	result.ProofCheck = buildSemiHonestVisualCheck(proof.Summary, proof.Data, req.ProofMode)
	result.Passed = result.TreeCheck.Passed && result.ProofCheck.Passed
	if result.Passed {
		result.Status = "passed"
	} else {
		result.Status = "failed_threshold"
	}
	return result
}

func (s *server) submitBatchUpdate(req ProofRunRequest, keyIDs []int64) (batchUpdateResponse, error) {
	endpoint := strings.TrimRight(req.LifecycleBaseURL, "/") + "/lifecycle/request/BATCH_UPDATE_KEYS"
	body := map[string]interface{}{
		"keyIds":     keyIDs,
		"user":       s.cfg.AcceptanceUser,
		"keyName":    "visual-tree-proof",
		"keyUse":     "tree-proof-acceptance",
		"keyDomain":  "acceptance",
		"autoUpdate": "false",
		"treeFanout": req.TreeFanout,
		"proofMode":  req.ProofMode,
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return batchUpdateResponse{}, err
	}
	httpReq, err := http.NewRequestWithContext(context.Background(), http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		return batchUpdateResponse{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "application/json")
	httpReq.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)

	resp, err := s.client.Do(httpReq)
	if err != nil {
		return batchUpdateResponse{}, fmt.Errorf("submit batch update failed: %w", err)
	}
	defer resp.Body.Close()
	var result batchUpdateResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return batchUpdateResponse{}, fmt.Errorf("decode batch update response failed: %w", err)
	}
	if resp.StatusCode >= http.StatusBadRequest {
		return result, fmt.Errorf("batch update api returned %d: %s", resp.StatusCode, result.Message)
	}
	return result, nil
}

func (s *server) waitBatchProof(batchID string, accepted int) (lifecycleProofResponse, error) {
	var latest lifecycleProofResponse
	deadline := time.Now().Add(time.Duration(s.cfg.VerifyWaitSeconds) * time.Second)
	if s.cfg.VerifyWaitSeconds <= 0 {
		deadline = time.Now().Add(30 * time.Second)
	}
	for {
		proof, err := s.fetchBatchProof(batchID)
		if err != nil {
			return proof, err
		}
		latest = proof
		if proof.Summary.VerifyStatus == "1" || proof.Summary.VerifyStatus == "2" {
			return proof, nil
		}
		if accepted > 0 && proof.Summary.ReceivedCount >= accepted && proof.Summary.BatchRoot != "" {
			return proof, nil
		}
		if time.Now().After(deadline) {
			return latest, nil
		}
		time.Sleep(2 * time.Second)
	}
}

func (s *server) fetchBatchProof(batchID string) (lifecycleProofResponse, error) {
	endpoint, err := url.Parse(s.cfg.LifecycleProofURL)
	if err != nil {
		return lifecycleProofResponse{}, fmt.Errorf("invalid lifecycle proof url: %w", err)
	}
	query := endpoint.Query()
	query.Set("batchId", batchID)
	query.Set("actionType", "UPDATE")
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return lifecycleProofResponse{}, err
	}
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)

	resp, err := s.client.Do(req)
	if err != nil {
		return lifecycleProofResponse{}, fmt.Errorf("query lifecycle proof failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= http.StatusBadRequest {
		return lifecycleProofResponse{}, fmt.Errorf("lifecycle proof api returned %d", resp.StatusCode)
	}

	var payload lifecycleProofResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return lifecycleProofResponse{}, fmt.Errorf("decode lifecycle proof payload failed: %w", err)
	}
	return payload, nil
}

func buildTreeVisualCheck(summary ProofSummary, records []ProofRecord) ProofCheck {
	details := []string{
		fmt.Sprintf("received leaves %d/%d", summary.ReceivedCount, summary.ExpectedCount),
		fmt.Sprintf("batch root %s", shortHash(summary.BatchRoot)),
	}
	seen := make(map[int]struct{}, len(records))
	pathsPresent := true
	for _, record := range records {
		if record.TreePath == "" || record.ParentBatchID == "" || record.RootBatchID == "" {
			pathsPresent = false
		}
		if _, ok := seen[record.NodeIndex]; ok {
			summary.DuplicateNodeIndex = true
		}
		seen[record.NodeIndex] = struct{}{}
	}
	passed := summary.BatchID != "" &&
		summary.ExpectedCount > 0 &&
		summary.ReceivedCount == summary.ExpectedCount &&
		!summary.DuplicateNodeIndex &&
		pathsPresent &&
		summary.BatchRoot != ""
	message := "tree batch has complete leaves, paths and root hash"
	if !passed {
		message = "tree batch is incomplete or has invalid node metadata"
	}
	return ProofCheck{Name: "tree-structure", Passed: passed, Message: message, Details: details}
}

func buildSemiHonestVisualCheck(summary ProofSummary, records []ProofRecord, proofMode string) ProofCheck {
	modeMatched := true
	for _, record := range records {
		if !strings.EqualFold(record.ProofMode, proofMode) {
			modeMatched = false
			break
		}
	}
	details := []string{
		fmt.Sprintf("commitments present %t", summary.AllCommitmentsPresent),
		fmt.Sprintf("consistency hashes present %t", summary.AllConsistencyHashesPresent),
		fmt.Sprintf("verify status %s", summary.VerifyStatus),
	}
	passed := summary.AllCommitmentsPresent &&
		summary.AllConsistencyHashesPresent &&
		summary.VerifyStatus == "1" &&
		summary.BatchRoot != "" &&
		modeMatched
	message := "commitments, consistency hashes and batch root are verified"
	if !passed {
		message = "proof metadata is missing or verification has not passed"
	}
	return ProofCheck{Name: "semi-honest-proof", Passed: passed, Message: message, Details: details}
}

func shortHash(value string) string {
	if len(value) <= 16 {
		return value
	}
	return value[:12] + "..." + value[len(value)-4:]
}

func (s *server) executeSecurityRun(caseID string) SecurityRunResult {
	return s.executeSecurityRunContext(context.Background(), caseID)
}

func (s *server) executeSecurityRunContext(parentCtx context.Context, caseID string) SecurityRunResult {
	if quantumModels[caseID] != "" {
		return s.executeQuantumSecurity(parentCtx, caseID)
	}
	if systemSecurityCases[caseID] {
		return s.executeSystemSecurity(parentCtx, caseID)
	}
	return SecurityRunResult{CaseID: caseID, Status: "error", Verdict: "not_applicable", Summary: "旧版或未知安全用例不适用于当前无密码系统，未计入验收"}
}

// Archived runner retained only for historical result interpretation, never routed from current UI/API.
func (s *server) executeArchivedSecurityRunContext(parentCtx context.Context, caseID string) SecurityRunResult {
	args := []string{
		s.securityScript,
		"--CaseId", caseID,
		"--Json",
		"--GenerateGoBaseUrl", s.scenarios["generate-tps"].BaseURL,
		"--LifecycleGoBaseUrl", s.scenarios["update-tps"].BaseURL,
		"--GenerateJavaBaseUrl", s.cfg.GenerateJavaBaseURL,
		"--LifecycleJavaBaseUrl", s.cfg.LifecycleJavaBaseURL,
		"--GenerateKeyPoolUrl", s.cfg.GenerateKeyPoolURL,
		"--LifecycleVerifyUrl", s.cfg.LifecycleVerifyURL,
		"--InternalToken", s.cfg.GenerateInternalToken,
		"--AcceptanceUser", s.cfg.AcceptanceUser,
		"--AttackUserName", s.cfg.AttackUserName,
		"--AttackUserPassword", s.cfg.AttackUserPassword,
		"--AttackAdminName", s.cfg.AttackAdminUserName,
		"--AttackAdminPassword", s.cfg.AttackAdminPassword,
		"--AttackForeignUser", s.cfg.AttackForeignUser,
	}

	ctx, cancel := context.WithTimeout(parentCtx, 90*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, s.bashPath, args...)

	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stdout
	execErr := cmd.Run()

	output := strings.TrimSpace(stdout.String())
	if output == "" {
		return SecurityRunResult{CaseID: caseID, Status: "error", Verdict: "error", Summary: "安全攻击脚本没有输出"}
	}

	jsonOutput := output
	if idx := strings.Index(output, "{"); idx > 0 {
		candidate := strings.TrimSpace(output[idx:])
		var probe map[string]interface{}
		if err := json.Unmarshal([]byte(candidate), &probe); err == nil {
			jsonOutput = candidate
		}
	}

	var result SecurityRunResult
	if err := json.Unmarshal([]byte(jsonOutput), &result); err != nil {
		if execErr != nil {
			return SecurityRunResult{CaseID: caseID, Status: "error", Verdict: "error", Summary: "安全攻击脚本执行失败且没有合法结果", Error: execErr.Error(), RawOutput: output}
		}
		return SecurityRunResult{
			CaseID:    caseID,
			Status:    "error",
			Verdict:   "error",
			Summary:   "安全攻击脚本输出不是合法 JSON",
			Error:     err.Error(),
			RawOutput: output,
		}
	}
	// 安全脚本在发现漏洞时按约定返回非零，但 JSON 结果仍然是可用的
	// 验收记录；只有没有结构化输出时才把进程退出码视为执行错误。
	if execErr != nil && result.Status == "" {
		result.Status = "error"
		result.Verdict = "error"
		result.Error = execErr.Error()
	}
	if result.CaseID == "" {
		result.CaseID = caseID
	}
	result.RawOutput = output
	return result
}

func (s *server) resolveScenario(base Scenario, req RunRequest) Scenario {
	resolved := base
	if req.Threads > 0 {
		resolved.Threads = req.Threads
	}
	if req.Connections > 0 {
		resolved.Connections = req.Connections
	}
	if req.DurationSec > 0 {
		resolved.DurationSeconds = req.DurationSec
	}
	if strings.TrimSpace(req.BaseURL) != "" {
		resolved.BaseURL = strings.TrimSpace(req.BaseURL)
	}
	if strings.TrimSpace(req.Path) != "" {
		resolved.Path = strings.TrimSpace(req.Path)
	}
	if len(req.Headers) > 0 {
		resolved.Headers = make(map[string]string)
		for _, header := range req.Headers {
			parts := strings.SplitN(header, ":", 2)
			if len(parts) != 2 {
				continue
			}
			resolved.Headers[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
		}
	}
	if strings.TrimSpace(req.Body) != "" {
		resolved.BodyTemplate = req.Body
	}
	return resolved
}

func (s *server) storeSecurityRun(run *SecurityRunResult) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.securityRuns[run.ID]; !exists {
		s.securityOrder = append(s.securityOrder, run.ID)
	}
	clone := *run
	s.securityRuns[run.ID] = &clone
}

func (s *server) storeProofRun(run *ProofRunResult) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.proofRuns[run.ID]; !exists {
		s.proofOrder = append(s.proofOrder, run.ID)
	}
	clone := *run
	s.proofRuns[run.ID] = &clone
}

func (s *server) nextID() string {
	seq := atomic.AddUint64(&s.counter, 1)
	return fmt.Sprintf("run-%s-%04d", time.Now().Format("20060102-150405"), seq)
}

func (s *server) storeRun(run *RunResult) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.runs[run.ID]; !exists {
		s.runOrder = append(s.runOrder, run.ID)
	}
	clone := *run
	s.runs[run.ID] = &clone
	if err := s.persistRunsLocked(); err != nil {
		log.Printf("persist runs failed: %v", err)
	}
}

func (s *server) loadRuns() error {
	if !fileExists(s.runsFile) {
		return nil
	}
	body, err := os.ReadFile(s.runsFile)
	if err != nil {
		return err
	}
	var data persistedRuns
	if err := json.Unmarshal(body, &data); err != nil {
		return err
	}
	for _, run := range data.Runs {
		s.runs[run.ID] = run
		s.runOrder = append(s.runOrder, run.ID)
	}
	return nil
}

func (s *server) loadAcceptanceEvidence() error {
	if !fileExists(s.acceptanceEvidenceFile) {
		return nil
	}
	body, err := os.ReadFile(s.acceptanceEvidenceFile)
	if err != nil {
		return err
	}
	var data persistedAcceptanceEvidence
	if err := json.Unmarshal(body, &data); err != nil {
		return err
	}
	for _, item := range data.Items {
		if item == nil || item.ID == "" {
			continue
		}
		s.acceptanceEvidence[item.ID] = item
		s.acceptanceEvidenceOrder = append(s.acceptanceEvidenceOrder, item.ID)
	}
	return nil
}

func (s *server) persistAcceptanceEvidenceLocked() error {
	items := make([]*AcceptanceEvidence, 0, len(s.acceptanceEvidenceOrder))
	for _, id := range s.acceptanceEvidenceOrder {
		items = append(items, s.acceptanceEvidence[id])
	}
	payload, err := json.MarshalIndent(persistedAcceptanceEvidence{Items: items}, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.acceptanceEvidenceFile, payload, 0o644)
}

func (s *server) persistRunsLocked() error {
	list := make([]*RunResult, 0, len(s.runOrder))
	for _, id := range s.runOrder {
		list = append(list, s.runs[id])
	}
	payload, err := json.MarshalIndent(persistedRuns{Runs: list}, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.runsFile, payload, 0o644)
}

func cloneHeaders(src map[string]string) map[string]string {
	dst := make(map[string]string, len(src))
	for key, value := range src {
		dst[key] = value
	}
	return dst
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func envOrDefaultInt(key string, fallback int) int {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func envOrDefaultBool(key string, fallback bool) bool {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func envOrDefaultFloat(key string, fallback float64) float64 {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil || parsed < 0 || parsed > 100 {
		return fallback
	}
	return parsed
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func parseFloat(raw string) float64 {
	raw = strings.TrimSpace(strings.TrimSuffix(raw, ","))
	value, _ := strconv.ParseFloat(raw, 64)
	return value
}

func parseInt64(raw string) int64 {
	value, _ := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
	return value
}

func parseDurationToMs(raw string) float64 {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 0
	}
	var unit string
	for _, suffix := range []string{"us", "ms", "s"} {
		if strings.HasSuffix(raw, suffix) {
			unit = suffix
			raw = strings.TrimSuffix(raw, suffix)
			break
		}
	}
	value := parseFloat(raw)
	switch unit {
	case "us":
		return value / 1000
	case "s":
		return value * 1000
	default:
		return value
	}
}

func lastField(line string) string {
	parts := strings.Fields(line)
	if len(parts) == 0 {
		return ""
	}
	return parts[len(parts)-1]
}

func init() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
}
