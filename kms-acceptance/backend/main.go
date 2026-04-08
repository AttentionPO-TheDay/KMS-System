package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
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
	MetricURL       string            `json:"metricUrl,omitempty"`
	MetricKind      string            `json:"metricKind,omitempty"`
	MetricTarget    float64           `json:"metricTarget,omitempty"`
	Description     string            `json:"description"`
	Notes           []string          `json:"notes,omitempty"`
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
	Status       string `json:"status"`
	Service      string `json:"service"`
	WrkAvailable bool   `json:"wrkAvailable"`
	WrkPath      string `json:"wrkPath,omitempty"`
	DataDir      string `json:"dataDir"`
	Now          string `json:"now"`
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

type server struct {
	mu             sync.RWMutex
	runs           map[string]*RunResult
	runOrder       []string
	scenarios      map[string]Scenario
	dataDir        string
	runsFile       string
	defaultWrkPath string
	counter        uint64
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

	srv := &server{
		runs:           make(map[string]*RunResult),
		scenarios:      defaultScenarios(),
		dataDir:        dataDir,
		runsFile:       filepath.Join(dataDir, "runs.json"),
		defaultWrkPath: detectWrkPath(wd),
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

	port := envOrDefault("PORT", "18090")
	log.Printf("kms-acceptance backend listening on :%s", port)
	log.Fatal(app.Listen(":" + port))
}

func defaultScenarios() map[string]Scenario {
	return map[string]Scenario{
		"generate-tps": {
			ID:              "generate-tps",
			Name:            "密钥生成 TPS",
			TargetTPS:       100000,
			Method:          http.MethodPost,
			BaseURL:         "http://127.0.0.1:8081",
			Path:            "/generate/request/ENROLL_KEY",
			DurationSeconds: 30,
			Threads:         12,
			Connections:     400,
			Headers: map[string]string{
				"Content-Type": "application/json",
			},
			BodyTemplate: `{"user":"acceptance_user","password":"123456","encryt_type":"无证书非对称加密","encryt_name":"SSCL","ua":"04e5df58dcdd1d8bba99bc62b825fd1abbb8b4c2d32aa4ed79f48bb5b1dd2e14e09f5d47296df715dd748951b6e22805b0e71bfd4097e7db93cd6528cb68870f2a","key_domain":"acceptance"}`,
			Description:  "使用 wrk 压测生成接入服务，目标 TPS 不低于 100000。",
			Notes:        []string{"建议在独立压测机执行。", "当前默认对接 kms-generate Go 接入服务。"},
		},
		"update-tps": {
			ID:              "update-tps",
			Name:            "密钥更新 TPS",
			TargetTPS:       5000,
			Method:          http.MethodPost,
			BaseURL:         "http://127.0.0.1:8082",
			Path:            "/lifecycle/request/UPDATE_KEY",
			DurationSeconds: 30,
			Threads:         12,
			Connections:     400,
			Headers: map[string]string{
				"Content-Type": "application/json",
				"Accept":       "application/json",
			},
			BodyTemplate: `{"keyId":10001,"user":"acceptance_user","password":"Test@123456"}`,
			Description:  "使用 wrk 压测更新接入服务，目标 TPS 不低于 5000。",
			MetricURL:    "http://127.0.0.1:8082/lifecycle/metrics",
			Notes:        []string{"当前默认 keyId 固定，若幂等开启建议在执行前改成大样本轮换脚本。"},
		},
		"revoke-tps": {
			ID:              "revoke-tps",
			Name:            "密钥回收 TPS",
			TargetTPS:       5000,
			Method:          http.MethodPost,
			BaseURL:         "http://127.0.0.1:8082",
			Path:            "/lifecycle/request/REVOKE_KEY",
			DurationSeconds: 30,
			Threads:         12,
			Connections:     400,
			Headers: map[string]string{
				"Content-Type": "application/json",
				"Accept":       "application/json",
			},
			BodyTemplate: `{"keyId":20001,"user":"acceptance_user","password":"Test@123456"}`,
			Description:  "使用 wrk 压测回收接入服务，目标 TPS 不低于 5000。",
			MetricURL:    "http://127.0.0.1:8082/lifecycle/metrics",
			Notes:        []string{"回收请求存在业务不可逆影响，正式执行前应准备专用测试数据。"},
		},
		"revoke-rate": {
			ID:              "revoke-rate",
			Name:            "密钥回收率",
			TargetTPS:       5000,
			Method:          http.MethodPost,
			BaseURL:         "http://127.0.0.1:8082",
			Path:            "/lifecycle/request/REVOKE_KEY",
			DurationSeconds: 30,
			Threads:         12,
			Connections:     400,
			Headers: map[string]string{
				"Content-Type": "application/json",
				"Accept":       "application/json",
			},
			BodyTemplate: `{"keyId":30001,"user":"acceptance_user","password":"Test@123456"}`,
			MetricURL:    "http://127.0.0.1:8082/lifecycle/metrics",
			MetricKind:   "revoke_accept_rate",
			MetricTarget: 98,
			Description:  "先压测回收请求，再从生命周期 metrics 计算受理回收率。后续可替换成最终业务回收率接口。",
			Notes:        []string{"当前按受理回收率计算，不等于最终业务回收完成率。", "后续建议在 Java 侧补最终回收统计接口后切换。"},
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
		if candidate == "" {
			continue
		}
		if path, err := exec.LookPath(candidate); err == nil {
			return path
		}
		if fileExists(candidate) {
			return candidate
		}
	}
	return ""
}

func (s *server) handleHealth(c *fiber.Ctx) error {
	wrkPath := s.defaultWrkPath
	return c.JSON(HealthResponse{
		Status:       "ok",
		Service:      "kms-acceptance-backend",
		WrkAvailable: wrkPath != "",
		WrkPath:      wrkPath,
		DataDir:      s.dataDir,
		Now:          time.Now().Format(time.RFC3339),
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

	wrkPath := strings.TrimSpace(req.WrkPath)
	if wrkPath == "" {
		wrkPath = s.defaultWrkPath
	}
	if wrkPath == "" {
		return c.Status(http.StatusServiceUnavailable).JSON(fiber.Map{"message": "wrk not found, set WRK_PATH or provide wrkPath"})
	}

	runID := s.nextID()
	run := &RunResult{
		ID:         runID,
		ScenarioID: resolved.ID,
		Scenario:   resolved.Name,
		Status:     "running",
		StartedAt:  time.Now().Format(time.RFC3339),
		TargetTPS:  resolved.TargetTPS,
		Notes:      append([]string{}, resolved.Notes...),
	}
	s.storeRun(run)

	result := s.executeRun(context.Background(), wrkPath, resolved)
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
	if err := os.WriteFile(luaFile, []byte(buildLuaScript(scenario.Method, scenario.Path, scenario.BodyTemplate, scenario.Headers)), 0o644); err != nil {
		return RunResult{Status: "failed", Error: "write lua script failed: " + err.Error()}
	}
	args = append(args, url)

	ctx, cancel := context.WithTimeout(parentCtx, time.Duration(scenario.DurationSeconds+20)*time.Second)
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
	metricCheck := collectMetricCheck(scenario)
	status := "passed"
	if !passedTPS || (metricCheck.Collected && !metricCheck.Passed) {
		status = "failed_threshold"
	}

	return RunResult{
		Status:      status,
		PassedTPS:   passedTPS,
		WrkCommand:  append([]string{wrkPath}, args...),
		Summary:     summary,
		MetricCheck: metricCheck,
	}
}

func buildLuaScript(method, path, body string, headers map[string]string) string {
	var headerLines []string
	for key, value := range headers {
		headerLines = append(headerLines, fmt.Sprintf("wrk.headers[%q] = %q", key, value))
	}
	sort.Strings(headerLines)
	return fmt.Sprintf("wrk.method = %q\n%s\nwrk.body = %q\nfunction request()\n  return wrk.format(%q, %q, wrk.headers, wrk.body)\nend\n", method, strings.Join(headerLines, "\n"), body, method, path)
}

func parseWrkOutput(output string) RunSummary {
	summary := RunSummary{RawOutput: output}
	for _, line := range strings.Split(output, "\n") {
		trimmed := strings.TrimSpace(line)
		switch {
		case strings.HasPrefix(trimmed, "Latency"):
			fields := strings.Fields(trimmed)
			if len(fields) >= 2 {
				summary.AvgLatencyMs = parseDurationToMs(fields[1])
			}
		case strings.HasPrefix(trimmed, "Req/Sec"):
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
		}
	}
	summary.P99LatencyMs = parseP99Latency(output)
	if summary.TotalRequests > 0 {
		summary.SuccessRate = 100
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

func collectMetricCheck(scenario Scenario) MetricCheck {
	if scenario.MetricURL == "" || scenario.MetricKind == "" {
		return MetricCheck{}
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, scenario.MetricURL, nil)
	if err != nil {
		return MetricCheck{Collected: false, Passed: false, Message: err.Error()}
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return MetricCheck{Collected: false, Passed: false, Source: scenario.MetricURL, Message: err.Error()}
	}
	defer resp.Body.Close()

	var payload map[string]float64
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return MetricCheck{Collected: false, Passed: false, Source: scenario.MetricURL, Message: err.Error()}
	}

	check := MetricCheck{
		Kind:       scenario.MetricKind,
		Target:     scenario.MetricTarget,
		Source:     scenario.MetricURL,
		Collected:  true,
		ReportedAt: time.Now().Format(time.RFC3339),
	}

	switch scenario.MetricKind {
	case "revoke_accept_rate":
		requests := payload["revoke_requests"]
		success := payload["revoke_success"]
		if requests <= 0 {
			check.Message = "metrics returned zero revoke_requests"
			return check
		}
		check.Value = success / requests * 100
		check.Passed = check.Value >= check.Target
		check.Message = "当前按受理回收率计算，后续应接入最终业务回收率。"
	default:
		check.Collected = false
		check.Message = "unsupported metric kind"
	}
	return check
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

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
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
