package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
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
	"github.com/gofiber/fiber/v2/middleware/cors"
)

const keyIDPlaceholder = "{{KEY_ID}}"

type Scenario struct {
	ID              string            `json:"id"`
	Name            string            `json:"name"`
	TargetTPS       float64           `json:"targetTps"`
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
	Description     string            `json:"description"`
	Notes           []string          `json:"notes,omitempty"`
	PreparedKeyIDs  []int64           `json:"-"`
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
}

type SecurityRunResult struct {
	ID         string                 `json:"id"`
	CaseID     string                 `json:"caseId"`
	Status     string                 `json:"status"`
	Verdict    string                 `json:"verdict"`
	Passed     bool                   `json:"passed"`
	StartedAt  string                 `json:"startedAt"`
	FinishedAt string                 `json:"finishedAt,omitempty"`
	Summary    string                 `json:"summary,omitempty"`
	Error      string                 `json:"error,omitempty"`
	Notes      []string               `json:"notes,omitempty"`
	Requests   []SecurityRequestTrace `json:"requests,omitempty"`
	RawOutput  string                 `json:"rawOutput,omitempty"`
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
	RequestsPerSec float64 `json:"requestsPerSec"`
	AvgLatencyMs   float64 `json:"avgLatencyMs"`
	P99LatencyMs   float64 `json:"p99LatencyMs"`
	TransferPerSec string  `json:"transferPerSec,omitempty"`
	TotalRequests  int64   `json:"totalRequests"`
	ReadBytes      string  `json:"readBytes,omitempty"`
	ErrorCount     int64   `json:"errorCount"`
	SuccessRate    float64 `json:"successRate"`
	RawOutput      string  `json:"rawOutput"`
}

type MetricCheck struct {
	Kind       string  `json:"kind,omitempty"`
	Value      float64 `json:"value,omitempty"`
	Target     float64 `json:"target,omitempty"`
	Passed     bool    `json:"passed"`
	Source     string  `json:"source,omitempty"`
	Message    string  `json:"message,omitempty"`
	Collected  bool    `json:"collected"`
	ReportedAt string  `json:"reportedAt,omitempty"`
}

type RunResult struct {
	ID          string      `json:"id"`
	ScenarioID  string      `json:"scenarioId"`
	Scenario    string      `json:"scenario"`
	Status      string      `json:"status"`
	StartedAt   string      `json:"startedAt"`
	FinishedAt  string      `json:"finishedAt,omitempty"`
	TargetTPS   float64     `json:"targetTps"`
	PassedTPS   bool        `json:"passedTps"`
	WrkCommand  []string    `json:"wrkCommand"`
	Summary     RunSummary  `json:"summary"`
	MetricCheck MetricCheck `json:"metricCheck"`
	Notes       []string    `json:"notes,omitempty"`
	Error       string      `json:"error,omitempty"`
}

type persistedRuns struct {
	Runs []*RunResult `json:"runs"`
}

type internalKeyRecord struct {
	KeyID     int64  `json:"keyId"`
	UserName  string `json:"userName"`
	Status    string `json:"status"`
	CreatedAt string `json:"createdAt"`
}

type internalGenerateResponse struct {
	Data []internalKeyRecord `json:"data"`
}

type internalVerifyRecord struct {
	KeyID       int64  `json:"keyId"`
	Exists      bool   `json:"exists"`
	Status      string `json:"status"`
	ChainStatus string `json:"chainStatus"`
	UpdatedAt   string `json:"updatedAt"`
}

type internalVerifyResponse struct {
	Data []internalVerifyRecord `json:"data"`
}

type acceptanceConfig struct {
	GenerateInternalToken  string
	GenerateKeyPoolURL     string
	LifecycleVerifyURL     string
	LifecycleProofURL      string
	GenerateJavaBaseURL    string
	LifecycleJavaBaseURL   string
	AcceptanceUser         string
	AttackUserName         string
	AttackUserPassword     string
	AttackAdminUserName    string
	AttackAdminPassword    string
	AttackForeignUser      string
	VerifyWaitSeconds      int
	KeyPoolLookbackMinutes int
	LifecycleRequiredKeys  int
	KeyPoolRetrySeconds    int
}

type server struct {
	mu             sync.RWMutex
	runs           map[string]*RunResult
	runOrder       []string
	securityRuns   map[string]*SecurityRunResult
	securityOrder  []string
	proofRuns      map[string]*ProofRunResult
	proofOrder     []string
	scenarios      map[string]Scenario
	dataDir        string
	runsFile       string
	defaultWrkPath string
	bashPath string
	securityScript string
	counter        uint64
	cfg            acceptanceConfig
	client         *http.Client
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
	srv := &server{
		runs:           make(map[string]*RunResult),
		securityRuns:   make(map[string]*SecurityRunResult),
		proofRuns:      make(map[string]*ProofRunResult),
		scenarios:      defaultScenarios(cfg),
		dataDir:        dataDir,
		runsFile:       filepath.Join(dataDir, "runs.json"),
		defaultWrkPath: detectWrkPath(wd),
		bashPath: detectBashPath(),
		securityScript: detectSecurityScriptPath(wd),
		cfg:            cfg,
		client:         &http.Client{Timeout: 30 * time.Second},
	}
	if err := srv.loadRuns(); err != nil {
		log.Printf("load runs failed: %v", err)
	}

	app := fiber.New()
	app.Use(cors.New())

	app.Get("/api/health", srv.handleHealth)
	app.Get("/api/scenarios", srv.handleScenarios)
	app.Get("/api/runs", srv.handleRuns)
	app.Get("/api/runs/:id", srv.handleRun)
	app.Post("/api/runs", srv.handleCreateRun)
	app.Get("/api/security/runs", srv.handleSecurityRuns)
	app.Post("/api/security/runs", srv.handleCreateSecurityRun)
	app.Get("/api/proof/runs", srv.handleProofRuns)
	app.Post("/api/proof/runs", srv.handleCreateProofRun)

	port := envOrDefault("PORT", "9090")
	log.Printf("kms-acceptance backend listening on :%s", port)
	log.Fatal(app.Listen(":" + port))
}

func loadAcceptanceConfig() acceptanceConfig {
	acceptanceUser := envOrDefault("ACCEPTANCE_USER", "acceptance_user")
	return acceptanceConfig{
		GenerateInternalToken:  envOrDefault("ACCEPTANCE_INTERNAL_TOKEN", envOrDefault("INTERNAL_TOKEN", "kms-generate-internal-secret-2026")),
		GenerateKeyPoolURL:     envOrDefault("ACCEPTANCE_GENERATE_KEY_POOL_URL", "http://127.0.0.1:9081/internal/generate/keys/recent"),
		LifecycleVerifyURL:     envOrDefault("ACCEPTANCE_LIFECYCLE_VERIFY_URL", "http://127.0.0.1:9082/internal/lifecycle/key-status"),
		LifecycleProofURL:      envOrDefault("ACCEPTANCE_LIFECYCLE_PROOF_URL", "http://127.0.0.1:9082/internal/lifecycle/batch-proof"),
		GenerateJavaBaseURL:    envOrDefault("ACCEPTANCE_GENERATE_JAVA_BASE_URL", "http://127.0.0.1:9081"),
		LifecycleJavaBaseURL:   envOrDefault("ACCEPTANCE_LIFECYCLE_JAVA_BASE_URL", "http://127.0.0.1:9082"),
		AcceptanceUser:         acceptanceUser,
		AttackUserName:         envOrDefault("ACCEPTANCE_ATTACK_USER_NAME", acceptanceUser),
		AttackUserPassword:     envOrDefault("ACCEPTANCE_ATTACK_USER_PASSWORD", ""),
		AttackAdminUserName:    envOrDefault("ACCEPTANCE_ATTACK_ADMIN_NAME", "admin"),
		AttackAdminPassword:    envOrDefault("ACCEPTANCE_ATTACK_ADMIN_PASSWORD", ""),
		AttackForeignUser:      envOrDefault("ACCEPTANCE_ATTACK_FOREIGN_USER", "admin"),
		VerifyWaitSeconds:      envOrDefaultInt("ACCEPTANCE_REVOKE_VERIFY_WAIT_SECONDS", 30),
		KeyPoolLookbackMinutes: envOrDefaultInt("ACCEPTANCE_KEY_POOL_LOOKBACK_MINUTES", 120),
		LifecycleRequiredKeys:  envOrDefaultInt("ACCEPTANCE_LIFECYCLE_REQUIRED_KEYS", 0),
		KeyPoolRetrySeconds:    envOrDefaultInt("ACCEPTANCE_KEY_POOL_RETRY_SECONDS", 30),
	}
}

func defaultScenarios(cfg acceptanceConfig) map[string]Scenario {
	generateBaseURL := envOrDefault("ACCEPTANCE_GENERATE_BASE_URL", "http://127.0.0.1:8081")
	lifecycleBaseURL := envOrDefault("ACCEPTANCE_LIFECYCLE_BASE_URL", "http://127.0.0.1:8082")
	tokenHeader := map[string]string{
		"Content-Type":     "application/json",
		"Accept":           "application/json",
		"X-Internal-Token": cfg.GenerateInternalToken,
	}

	return map[string]Scenario{
		"generate-tps": {
			ID:              "generate-tps",
			Name:            "密钥生成 TPS",
			TargetTPS:       100000,
			Method:          http.MethodPost,
			BaseURL:         generateBaseURL,
			Path:            "/generate/request/ENROLL_KEY",
			DurationSeconds: 1,
			Threads:         2,
			Connections:     340,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"user":"%s","encryt_type":"无证书非对称加密","encryt_name":"SSCL","ua":"04e5df58dcdd1d8bba99bc62b825fd1abbb8b4c2d32aa4ed79f48bb5b1dd2e14e09f5d47296df715dd748951b6e22805b0e71bfd4097e7db93cd6528cb68870f2a","key_domain":"acceptance","key_name":"acceptance-load","key_use":"性能验收","auto_update":"false"}`, cfg.AcceptanceUser),
			Description:     "直接压测 kms-generate Go 接口，默认携带内部 token，目标 TPS 不低于 100000。",
			Notes:           []string{"默认使用 1 秒短压，优先控制总生成量，同时保持明显高于 10 万 TPS 的余量。", "更新和回收场景会复用该用户最新生成的 key 池。"},
		},
		"update-tps": {
			ID:              "update-tps",
			Name:            "密钥更新 TPS",
			TargetTPS:       5000,
			Method:          http.MethodPost,
			BaseURL:         lifecycleBaseURL,
			Path:            "/lifecycle/request/UPDATE_KEY",
			DurationSeconds: 5,
			Threads:         2,
			Connections:     50,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"keyId":%s,"user":"%s","keyName":"acceptance-rotate","keyUse":"性能验收","keyDomain":"acceptance","autoUpdate":"false"}`, keyIDPlaceholder, cfg.AcceptanceUser),
			Description:     "直接压测 kms-updatedel Go 接口，自动从最新生成结果加载 key 池，目标 TPS 不低于 5000。",
			Notes:           []string{"执行前请先跑一次生成场景，准备足够的 keyId。", "默认按 5 秒窗口控制单轮 key 需求，避免过度消耗生成结果。"},
		},
		"revoke-tps": {
			ID:              "revoke-tps",
			Name:            "密钥回收 TPS",
			TargetTPS:       5000,
			Method:          http.MethodPost,
			BaseURL:         lifecycleBaseURL,
			Path:            "/lifecycle/request/REVOKE_KEY",
			DurationSeconds: 5,
			Threads:         2,
			Connections:     50,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"keyId":%s,"user":"%s"}`, keyIDPlaceholder, cfg.AcceptanceUser),
			Description:     "直接压测 kms-updatedel Go 接口，自动复用最新生成 key 池，目标 TPS 不低于 5000。",
			Notes:           []string{"回收请求不可逆，请确保使用验收专用 key。", "默认按 5 秒窗口控制单轮 key 需求，避免和生成尾部处理相互挤压。"},
		},
		"revoke-rate": {
			ID:              "revoke-rate",
			Name:            "密钥回收率",
			TargetTPS:       5000,
			Method:          http.MethodPost,
			BaseURL:         lifecycleBaseURL,
			Path:            "/lifecycle/request/REVOKE_KEY",
			DurationSeconds: 5,
			Threads:         2,
			Connections:     50,
			Headers:         cloneHeaders(tokenHeader),
			BodyTemplate:    fmt.Sprintf(`{"keyId":%s,"user":"%s"}`, keyIDPlaceholder, cfg.AcceptanceUser),
			MetricKind:      "revoke_final_rate",
			MetricTarget:    98,
			Description:     "先执行回收压测，再去生命周期 Java 内部查询最终状态，按 status=3 计算最终回收率。",
			Notes:           []string{"默认等待 30 秒后核验，可通过环境变量调整。", "默认按 5 秒窗口控制单轮 key 需求，避免最终核验被生成尾部长期拖慢。"},
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
		SecurityScriptPath: s.securityScript,
		SecurityExecutable: s.bashPath,
		SecurityAvailable:  s.bashPath != "" && s.securityScript != "",
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
	if s.bashPath == "" {
		return c.Status(http.StatusServiceUnavailable).JSON(fiber.Map{"message": "bash not found"})
	}
	if s.securityScript == "" {
		return c.Status(http.StatusServiceUnavailable).JSON(fiber.Map{"message": "security_test.sh not found"})
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
	run.RawOutput = result.RawOutput
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
	if !ok {
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

	result := s.executeRun(context.Background(), wrkPath, prepared)
	run.Status = result.Status
	run.FinishedAt = time.Now().Format(time.RFC3339)
	run.PassedTPS = result.PassedTPS
	run.Summary = result.Summary
	run.WrkCommand = result.WrkCommand
	run.Error = result.Error
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
	prepared := base
	var notes []string

	if !strings.Contains(prepared.BodyTemplate, keyIDPlaceholder) {
		return prepared, notes, nil
	}

	requiredKeys := s.cfg.LifecycleRequiredKeys
	if requiredKeys <= 0 {
		requiredKeys = int(prepared.TargetTPS * float64(prepared.DurationSeconds))
	}
	if requiredKeys <= 0 {
		requiredKeys = prepared.Connections
	}

	createdAfter := s.latestGenerateStartedAt()
	if createdAfter.IsZero() {
		createdAfter = time.Now().Add(-time.Duration(s.cfg.KeyPoolLookbackMinutes) * time.Minute)
		notes = append(notes, fmt.Sprintf("未找到最近一次生成压测记录，回退到最近 %d 分钟生成数据取 key 池。", s.cfg.KeyPoolLookbackMinutes))
	} else {
		notes = append(notes, fmt.Sprintf("复用最近一次生成压测开始时间 %s 之后的 key 池。", createdAfter.Format(time.RFC3339)))
	}

	keyIDs, err := s.fetchGeneratedKeyIDs(requiredKeys, createdAfter, "")
	if err != nil {
		return prepared, notes, err
	}
	prepared.PreparedKeyIDs = keyIDs
	notes = append(notes, fmt.Sprintf("已装载 %d 个 keyId 作为 wrk 轮换池。", len(keyIDs)))
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
	if limit <= 0 {
		return nil, fmt.Errorf("invalid key pool size")
	}

	deadline := time.Now().Add(time.Duration(s.cfg.KeyPoolRetrySeconds) * time.Second)
	if s.cfg.KeyPoolRetrySeconds <= 0 {
		deadline = time.Now()
	}

	var lastErr error
	for {
		keyIDs, err := s.fetchGeneratedKeyIDsOnce(limit, createdAfter, encrytName)
		if err == nil {
			return keyIDs, nil
		}
		lastErr = err
		if time.Now().After(deadline) {
			return nil, lastErr
		}
		time.Sleep(2 * time.Second)
	}
}

func (s *server) fetchGeneratedKeyIDsOnce(limit int, createdAfter time.Time, encrytName string) ([]int64, error) {
	endpoint, err := url.Parse(s.cfg.GenerateKeyPoolURL)
	if err != nil {
		return nil, fmt.Errorf("invalid generate key pool url: %w", err)
	}
	query := endpoint.Query()
	query.Set("userName", s.cfg.AcceptanceUser)
	query.Set("limit", strconv.Itoa(limit))
	if !createdAfter.IsZero() {
		query.Set("createdAfter", createdAfter.Format(time.RFC3339))
	}
	if strings.TrimSpace(encrytName) != "" {
		query.Set("encrytName", strings.TrimSpace(encrytName))
	}
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, endpoint.String(), nil)
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
	passedTPS := summary.RequestsPerSec >= scenario.TargetTPS
	metricCheck := s.collectMetricCheck(scenario)
	status := "passed"
	if !passedTPS || (metricCheck.Collected && !metricCheck.Passed) {
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
	summary.ErrorCount = socketErrors + non2xx
	totalAttempts := summary.TotalRequests + socketErrors
	successful := summary.TotalRequests - non2xx
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
	if scenario.MetricKind != "revoke_final_rate" {
		return MetricCheck{}
	}
	if len(scenario.PreparedKeyIDs) == 0 {
		return MetricCheck{Kind: scenario.MetricKind, Target: scenario.MetricTarget, Message: "no key ids prepared", Source: s.cfg.LifecycleVerifyURL}
	}

	verified, err := s.waitRevokedKeys(scenario.PreparedKeyIDs)
	if err != nil {
		return MetricCheck{Kind: scenario.MetricKind, Target: scenario.MetricTarget, Source: s.cfg.LifecycleVerifyURL, Message: err.Error()}
	}
	value := float64(verified) / float64(len(scenario.PreparedKeyIDs)) * 100
	return MetricCheck{
		Kind:       scenario.MetricKind,
		Value:      value,
		Target:     scenario.MetricTarget,
		Passed:     value >= scenario.MetricTarget,
		Source:     s.cfg.LifecycleVerifyURL,
		Collected:  true,
		ReportedAt: time.Now().Format(time.RFC3339),
		Message:    fmt.Sprintf("最终状态核验通过 %d/%d", verified, len(scenario.PreparedKeyIDs)),
	}
}

func (s *server) waitRevokedKeys(keyIDs []int64) (int, error) {
	deadline := time.Now().Add(time.Duration(s.cfg.VerifyWaitSeconds) * time.Second)
	if s.cfg.VerifyWaitSeconds <= 0 {
		deadline = time.Now()
	}

	var (
		latest  int
		lastErr error
	)
	for {
		verified, err := s.verifyRevokedKeysOnce(keyIDs)
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

func (s *server) verifyRevokedKeysOnce(keyIDs []int64) (int, error) {
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
			if item.Exists && item.Status == "3" {
				verified++
			}
		}
	}
	return verified, nil
}

func (s *server) fetchLifecycleStatuses(keyIDs []int64) ([]internalVerifyRecord, error) {
	endpoint, err := url.Parse(s.cfg.LifecycleVerifyURL)
	if err != nil {
		return nil, fmt.Errorf("invalid lifecycle verify url: %w", err)
	}
	query := endpoint.Query()
	for _, keyID := range keyIDs {
		query.Add("keyIds", strconv.FormatInt(keyID, 10))
	}
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, endpoint.String(), nil)
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

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, s.bashPath, args...)

	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stdout
	if err := cmd.Run(); err != nil {
		return SecurityRunResult{
			CaseID:    caseID,
			Status:    "error",
			Verdict:   "error",
			Summary:   "安全攻击脚本执行失败",
			Error:     err.Error(),
			RawOutput: stdout.String(),
		}
	}

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
		return SecurityRunResult{
			CaseID:    caseID,
			Status:    "error",
			Verdict:   "error",
			Summary:   "安全攻击脚本输出不是合法 JSON",
			Error:     err.Error(),
			RawOutput: output,
		}
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
