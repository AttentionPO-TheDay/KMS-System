package main

import (
	"bytes"
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

const scopedUnavailable = "该场景尚无受控测试节点/fixture执行能力；禁止使用内部令牌代替节点权限。"
const boundaryProbeID = "demo-boundary-probe"

var demoRunPath = regexp.MustCompile(`^/api/runs/(run-[A-Za-z0-9-]+)(/cancel)?$`)
var demoSecurityRunPath = regexp.MustCompile(`^/api/security/runs/(run-[A-Za-z0-9-]+)(/cancel)?$`)
var demoLifecyclePath = regexp.MustCompile(`^/api/acceptance/lifecycle/run-[A-Za-z0-9-]+$`)

type demoIdentity struct {
	OK              bool            `json:"ok"`
	EntryMode       string          `json:"entryMode"`
	PrincipalType   string          `json:"principalType"`
	UserID          json.RawMessage `json:"userId"`
	SessionRevision json.RawMessage `json:"sessionRevision"`
}

type demoJob struct {
	session   string
	revision  int64
	lease     string
	cancel    context.CancelFunc
	done      chan struct{}
	result    RunResult
	audit     *lifecycleArchive
	auditRows []lifecycleRow
}

type demoSecurityJob struct {
	session  string
	revision int64
	lease    string
	cancel   context.CancelFunc
	done     chan struct{}
	result   SecurityRunResult
}

type demoEvidence struct {
	session  string
	revision int64
	payload  fiber.Map
}

type demoGuard struct {
	server             *server
	enabled            bool
	token              string
	authority          string
	hosts              map[string]bool
	origins            map[string]bool
	mu                 sync.RWMutex
	jobs               map[string]*demoJob
	jobOrder           []string
	securityJobs       map[string]*demoSecurityJob
	securityJobOrder   []string
	evidence           []demoEvidence
	executeRun         func(context.Context, string, Scenario) RunResult
	executeSecurityRun func(context.Context, string) SecurityRunResult
}

func demoAllowlist(name, fallback string) map[string]bool {
	out := map[string]bool{}
	for _, value := range strings.Split(envOrDefault(name, fallback), ",") {
		out[strings.TrimSpace(value)] = true
	}
	return out
}

func newDemoGuard(s *server) *demoGuard {
	g := &demoGuard{server: s, enabled: envOrDefaultBool("KMS_DEMO_ENABLED", false),
		token:     envOrDefault("INTERNAL_TOKEN", s.cfg.GenerateInternalToken),
		authority: strings.TrimRight(s.cfg.LifecycleJavaBaseURL, "/") + "/internal/lifecycle/demo/",
		hosts:     demoAllowlist("KMS_DEMO_ALLOWED_HOSTS", "127.0.0.1:8088,localhost:8088"),
		origins:   demoAllowlist("KMS_DEMO_ALLOWED_ORIGINS", "http://127.0.0.1:8088,http://localhost:8088"),
		jobs:      map[string]*demoJob{}, securityJobs: map[string]*demoSecurityJob{}}
	g.executeRun = s.executeRun
	g.executeSecurityRun = s.executeSecurityRunContext
	return g
}

type demoRPCError struct {
	status  int
	message string
}

func (e *demoRPCError) Error() string { return e.message }

func (g *demoGuard) rpc(ctx context.Context, action string, payload map[string]interface{}) (map[string]json.RawMessage, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, g.authority+action, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Internal-Token", g.token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := g.server.client.Do(req)
	if err != nil {
		return nil, &demoRPCError{503, "Demo 身份服务暂时不可用"}
	}
	defer resp.Body.Close()
	var envelope struct {
		Code int                        `json:"code"`
		Data map[string]json.RawMessage `json:"data"`
	}
	if resp.StatusCode != 200 || json.NewDecoder(io.LimitReader(resp.Body, 65536)).Decode(&envelope) != nil || envelope.Code != 200 {
		return nil, &demoRPCError{503, "Demo 身份服务暂时不可用"}
	}
	var ok bool
	_ = json.Unmarshal(envelope.Data["ok"], &ok)
	if !ok {
		var code string
		_ = json.Unmarshal(envelope.Data["errorCode"], &code)
		return nil, &demoRPCError{409, "Demo 会话不可用或版本已失效: " + code}
	}
	return envelope.Data, nil
}

func demoFailure(c *fiber.Ctx, err error) error {
	var rpcErr *demoRPCError
	if errors.As(err, &rpcErr) {
		return c.Status(rpcErr.status).JSON(fiber.Map{"message": rpcErr.message})
	}
	return c.Status(503).JSON(fiber.Map{"message": "Demo 身份服务暂时不可用"})
}

func adminIdentity(data map[string]json.RawMessage, nested bool, revision int64) bool {
	var identity demoIdentity
	raw, _ := json.Marshal(data)
	if nested {
		raw = data["identity"]
	}
	if json.Unmarshal(raw, &identity) != nil {
		return false
	}
	return identity.EntryMode == "DEMO" && identity.PrincipalType == "ADMIN" && len(identity.UserID) > 0 && string(identity.UserID) != "null" && string(identity.SessionRevision) == strconv.FormatInt(revision, 10)
}

func canonicalDemoRoute(method, path string) bool {
	if method == http.MethodGet {
		switch path {
		case "/api/health", "/api/scenarios", "/api/runs", "/api/security/runs", "/api/proof/runs", "/api/acceptance/criteria", "/api/acceptance/evidence", "/api/acceptance/lifecycle":
			return true
		}
		match := demoRunPath.FindStringSubmatch(path)
		if len(match) > 0 && match[2] == "" {
			return true
		}
		match = demoSecurityRunPath.FindStringSubmatch(path)
		return (len(match) > 0 && match[2] == "") || demoLifecyclePath.MatchString(path)
	}
	if method == http.MethodPost {
		switch path {
		case "/api/runs", "/api/security/runs", "/api/proof/runs", "/api/acceptance/evidence":
			return true
		}
		match := demoRunPath.FindStringSubmatch(path)
		if len(match) > 0 && match[2] == "/cancel" {
			return true
		}
		match = demoSecurityRunPath.FindStringSubmatch(path)
		return len(match) > 0 && match[2] == "/cancel"
	}
	return false
}

func demoScenarioAllowed(id string) bool {
	switch id {
	case "generate-tps", "update-tps", "revoke-tps", "revoke-rate":
		return true
	default:
		return false
	}
}

func demoSecurityCaseAllowed(id string) bool {
	for _, criterion := range acceptanceCriteria() {
		if criterion.Kind != "security-suite" {
			continue
		}
		for _, caseID := range criterion.CaseIDs {
			if id == caseID {
				return true
			}
		}
	}
	return false
}

func decodeStrictJSON(body []byte, target interface{}) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return errors.New("request must contain exactly one JSON object")
	}
	return nil
}

// This middleware is the ingress boundary, not CORS. Legacy handlers cannot be
// reached by a browser with an internal credential or arbitrary execution target.
func (g *demoGuard) authorize(c *fiber.Ctx) error {
	supplied := c.Get("X-Kms-Demo-Gateway")
	if !g.enabled || g.token == "" || supplied == "" || subtle.ConstantTimeCompare([]byte(g.token), []byte(supplied)) != 1 || c.Get("X-Kms-Entry-Mode") != "demo" || !g.hosts[string(c.Request().URI().Host())] {
		return c.Status(404).JSON(fiber.Map{"message": "受控 Demo 网关必需"})
	}
	rawURI := string(c.Request().Header.RequestURI())
	path := string(c.Request().URI().PathOriginal())
	if !strings.HasPrefix(rawURI, "/") || strings.HasPrefix(rawURI, "//") || path != c.Path() || !canonicalDemoRoute(c.Method(), path) || c.Get("Authorization") != "" || c.Get("X-Internal-Token") != "" {
		return c.Status(404).JSON(fiber.Map{"message": "验收端点未开放"})
	}
	if len(c.Body()) > 16384 {
		return c.Status(413).JSON(fiber.Map{"message": "验收请求超过边界"})
	}
	origin := c.Get("Origin")
	if (origin != "" && !g.origins[origin]) || (c.Method() == http.MethodPost && !g.origins[origin]) {
		return c.Status(403).JSON(fiber.Map{"message": "Demo 来源不受信任"})
	}
	cookieRequest := &http.Request{Header: http.Header{"Cookie": []string{c.Get("Cookie")}}}
	session := ""
	cookieCount := 0
	for _, cookie := range cookieRequest.Cookies() {
		if cookie.Name == "KMS-Demo-Session" {
			cookieCount++
			if cookieCount > 1 {
				return c.Status(401).JSON(fiber.Map{"message": "Demo 会话 Cookie 不唯一"})
			}
			session = cookie.Value
		}
	}
	revisionText := c.Get("X-Kms-Demo-Revision")
	revision, err := strconv.ParseInt(revisionText, 10, 64)
	if session == "" || len(session) > 256 || err != nil || revision < 0 || strconv.FormatInt(revision, 10) != revisionText {
		return c.Status(401).JSON(fiber.Map{"message": "缺少 Demo 会话或版本"})
	}
	payload := map[string]interface{}{"sessionId": session, "revision": revision}
	csrf := c.Get("X-Kms-Demo-CSRF")
	if c.Method() == http.MethodPost {
		if csrf == "" {
			return c.Status(403).JSON(fiber.Map{"message": "缺少 Demo CSRF 凭据"})
		}
		payload["csrfToken"] = csrf
	}
	data, err := g.rpc(context.Background(), "introspect", payload)
	if err != nil {
		return demoFailure(c, err)
	}
	if !adminIdentity(data, false, revision) {
		return c.Status(403).JSON(fiber.Map{"message": "验收平台仅允许 ADMIN"})
	}
	if c.Method() == http.MethodGet {
		return g.read(c, session, revision)
	}
	if match := demoRunPath.FindStringSubmatch(path); len(match) > 0 {
		return g.cancelJob(c, match[1], session, revision)
	}
	if match := demoSecurityRunPath.FindStringSubmatch(path); len(match) > 0 {
		return g.cancelSecurityJob(c, match[1], session, revision)
	}
	data, err = g.rpc(context.Background(), "lease/acquire", payload)
	if err != nil {
		return demoFailure(c, err)
	}
	var lease string
	_ = json.Unmarshal(data["leaseId"], &lease)
	if lease == "" {
		return c.Status(503).JSON(fiber.Map{"message": "Demo 租约未建立"})
	}
	transferred := false
	defer func() {
		if !transferred {
			g.release(session, lease)
		}
	}()
	if !adminIdentity(data, true, revision) {
		return c.Status(403).JSON(fiber.Map{"message": "租约身份必须为 ADMIN"})
	}
	if path == "/api/acceptance/evidence" {
		var req AcceptanceEvidenceRequest
		decoder := json.NewDecoder(bytes.NewReader(c.Body()))
		decoder.DisallowUnknownFields()
		if len(c.Body()) > 16384 || decoder.Decode(&req) != nil || decoder.Decode(&struct{}{}) != io.EOF || len(req.Evidence) > 4000 {
			return c.Status(400).JSON(fiber.Map{"message": "证据仅接受有界现场测量和说明，不接受身份或密钥材料字段"})
		}
		// The legacy local evidence recorder is retained, but its file write is
		// fenced and manual claims are not promoted into verified successes.
		if _, err := g.rpc(context.Background(), "lease/validate", map[string]interface{}{"sessionId": session, "leaseId": lease}); err != nil {
			return demoFailure(c, err)
		}
		if err := c.Next(); err != nil {
			return err
		}
		if c.Response().StatusCode() >= 400 {
			return nil
		}
		var recorded fiber.Map
		if json.Unmarshal(c.Response().Body(), &recorded) != nil {
			return c.Status(503).JSON(fiber.Map{"message": "证据记录返回无效"})
		}
		recorded["thresholdMet"] = recorded["passed"]
		recorded["passed"] = false
		recorded["verified"] = false
		recorded["source"] = "manual-reported"
		g.mu.Lock()
		g.evidence = append(g.evidence, demoEvidence{session: session, revision: revision, payload: recorded})
		g.mu.Unlock()
		return c.JSON(recorded)
	}
	if path == "/api/runs" {
		var req struct {
			ScenarioID string `json:"scenarioId"`
		}
		if decodeStrictJSON(c.Body(), &req) != nil {
			return c.Status(400).JSON(fiber.Map{"message": "只允许固定场景，不允许 URL/body/headers/executable 覆盖"})
		}
		if req.ScenarioID == boundaryProbeID {
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
			job := &demoJob{session: session, revision: revision, lease: lease, cancel: cancel, done: make(chan struct{}), result: RunResult{ID: g.server.nextID(), ScenarioID: boundaryProbeID, Scenario: "Demo 权威与入口边界探针", Status: "running", Stage: "校验权威边界", StartedAt: time.Now().Format(time.RFC3339)}}
			g.addJob(job)
			transferred = true
			go g.executeProbe(ctx, job)
			return c.Status(202).JSON(job.result)
		}
		if !demoScenarioAllowed(req.ScenarioID) {
			return c.Status(400).JSON(fiber.Map{"message": "未知或未授权的验收场景"})
		}
		scenario, ok := g.server.scenarios[req.ScenarioID]
		if !ok {
			return c.Status(503).JSON(fiber.Map{"message": "固定验收场景未配置"})
		}
		wrkPath, ok := resolveExecutable(g.server.defaultWrkPath)
		if !ok {
			return c.Status(503).JSON(fiber.Map{"message": "wrk 不可用，无法启动性能验收"})
		}
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(scenario.DurationSeconds+90)*time.Second)
		job := &demoJob{session: session, revision: revision, lease: lease, cancel: cancel, done: make(chan struct{}), result: RunResult{ID: g.server.nextID(), ScenarioID: scenario.ID, Scenario: scenario.Name, Status: "preparing", Stage: "准备固定场景", StartedAt: time.Now().Format(time.RFC3339), TargetTPS: scenario.TargetTPS}}
		g.addJob(job)
		transferred = true
		go g.executePerformance(ctx, job, wrkPath, scenario)
		return c.Status(202).JSON(job.result)
	}
	if path == "/api/security/runs" {
		var req SecurityRunRequest
		if decodeStrictJSON(c.Body(), &req) != nil {
			return c.Status(400).JSON(fiber.Map{"message": "只允许提交固定 caseId"})
		}
		req.CaseID = strings.TrimSpace(req.CaseID)
		if !demoSecurityCaseAllowed(req.CaseID) {
			return c.Status(400).JSON(fiber.Map{"message": "未知或未授权的安全验收用例"})
		}
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		job := &demoSecurityJob{session: session, revision: revision, lease: lease, cancel: cancel, done: make(chan struct{}), result: SecurityRunResult{ID: g.server.nextID(), CaseID: req.CaseID, Status: "preparing", Stage: "准备安全用例", StartedAt: time.Now().Format(time.RFC3339)}}
		g.addSecurityJob(job)
		transferred = true
		go g.executeSecurity(ctx, job)
		return c.Status(202).JSON(job.result)
	}
	return c.Status(503).JSON(fiber.Map{"message": scopedUnavailable})
}

func (g *demoGuard) release(session, lease string) bool {
	if _, err := g.rpc(context.Background(), "lease/release", map[string]interface{}{"sessionId": session, "leaseId": lease}); err != nil {
		// Never clear the authority's inflight fence locally on a failed release.
		log.Print("Demo lease release failed; authority fence remains until expiry")
		return false
	}
	return true
}

func (g *demoGuard) addJob(job *demoJob) {
	g.mu.Lock()
	g.jobs[job.result.ID] = job
	g.jobOrder = append(g.jobOrder, job.result.ID)
	g.mu.Unlock()
}

func (g *demoGuard) addSecurityJob(job *demoSecurityJob) {
	g.mu.Lock()
	g.securityJobs[job.result.ID] = job
	g.securityJobOrder = append(g.securityJobOrder, job.result.ID)
	g.mu.Unlock()
}

func (g *demoGuard) validateBinding(ctx context.Context, session string, revision int64, lease string) error {
	if _, err := g.rpc(ctx, "lease/validate", map[string]interface{}{"sessionId": session, "leaseId": lease}); err != nil {
		return err
	}
	data, err := g.rpc(ctx, "introspect", map[string]interface{}{"sessionId": session, "revision": revision})
	if err != nil {
		return err
	}
	if !adminIdentity(data, false, revision) {
		return errors.New("Demo ADMIN 身份已失效")
	}
	return nil
}

func (g *demoGuard) watchBinding(ctx context.Context, session string, revision int64, lease string, cancel context.CancelFunc) (chan struct{}, <-chan error) {
	stop := make(chan struct{})
	done := make(chan error, 1)
	go func() {
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-stop:
				done <- nil
				return
			case <-ctx.Done():
				done <- nil
				return
			case <-ticker.C:
				if err := g.validateBinding(context.Background(), session, revision, lease); err != nil {
					cancel()
					done <- err
					return
				}
			}
		}
	}()
	return stop, done
}

func (g *demoGuard) updateRunStage(job *demoJob, status, stage string) {
	g.mu.Lock()
	job.result.Status = status
	job.result.Stage = "结果已归档"
	job.result.Stage = stage
	g.mu.Unlock()
}

func (g *demoGuard) updateSecurityStage(job *demoSecurityJob, status, stage string) {
	g.mu.Lock()
	job.result.Status = status
	job.result.Stage = stage
	g.mu.Unlock()
}

func (g *demoGuard) redact(value string, limit int) string {
	secrets := []string{g.token, g.server.cfg.GenerateInternalToken, g.server.cfg.AttackUserPassword, g.server.cfg.AttackAdminPassword}
	for _, scenario := range g.server.scenarios {
		for _, headerValue := range scenario.Headers {
			secrets = append(secrets, headerValue)
		}
	}
	for _, secret := range secrets {
		if strings.TrimSpace(secret) != "" {
			value = strings.ReplaceAll(value, secret, "[REDACTED]")
		}
	}
	if limit > 0 && len(value) > limit {
		return value[:limit] + "\n...[输出已截断]"
	}
	return value
}

func (g *demoGuard) sanitizeRunResult(result RunResult) RunResult {
	result.WrkCommand = nil
	result.Summary.RawOutput = g.redact(result.Summary.RawOutput, 6000)
	result.Error = g.redact(result.Error, 1000)
	return result
}

func (g *demoGuard) sanitizeSecurityResult(result SecurityRunResult) SecurityRunResult {
	result.RawOutput = g.redact(result.RawOutput, 6000)
	result.Error = g.redact(result.Error, 1000)
	for index := range result.Requests {
		result.Requests[index].ResponseBody = g.redact(result.Requests[index].ResponseBody, 1000)
		result.Requests[index].Message = g.redact(result.Requests[index].Message, 500)
	}
	return result
}

func (g *demoGuard) executePerformance(ctx context.Context, job *demoJob, wrkPath string, scenario Scenario) {
	result := job.result
	result.Status = "failed"
	result.Stage = "启动前核验"
	if err := g.validateBinding(ctx, job.session, job.revision, job.lease); err != nil {
		result.Error = "启动前权威校验失败: " + err.Error()
		g.finishPerformance(job, result)
		return
	}

	prepared, notes, err := g.server.prepareScenario(scenario)
	if err != nil {
		result.Error = err.Error()
		result.Notes = append(result.Notes, "固定场景准备失败，未启动 wrk。")
		g.finishPerformance(job, result)
		return
	}
	job.audit, job.auditRows, err = g.server.beginLifecycleAudit(ctx, prepared, result, job.session, job.revision)
	if err != nil {
		result.Error = "无法记录验收密钥初始状态，未启动压测：" + err.Error()
		g.finishPerformance(job, result)
		return
	}
	if ctx.Err() != nil {
		result.Status = "cancelled"
		result.Stage = "已取消"
		result.Error = "任务在准备阶段被取消"
		g.finishPerformance(job, result)
		return
	}

	g.updateRunStage(job, "running", "执行固定性能场景")
	stopWatch, watchDone := g.watchBinding(ctx, job.session, job.revision, job.lease, job.cancel)
	executed := g.executeRun(ctx, wrkPath, prepared)
	if err := g.server.finishLifecycleAudit(ctx, job.audit, job.auditRows, executed); err != nil {
		executed.Status = "failed"
		executed.Error = "验收生命周期归档失败，结果不予采信"
	}
	executed = applyLifecycleAuditResult(prepared, job.audit, executed)
	close(stopWatch)
	watchErr := <-watchDone
	executed = g.sanitizeRunResult(executed)
	result.Status = executed.Status
	result.Stage = "核验执行结果"
	result.PassedTPS = executed.PassedTPS
	result.Summary = executed.Summary
	result.MetricCheck = executed.MetricCheck
	result.Error = executed.Error
	result.Notes = append(append(append([]string{}, scenario.Notes...), notes...), executed.Notes...)
	if watchErr != nil {
		result.Status = "failed"
		result.Error = "执行期间 Demo 权威失效，任务已终止"
		result.Notes = append(result.Notes, watchErr.Error())
	} else if errors.Is(ctx.Err(), context.Canceled) {
		result.Status = "cancelled"
		result.Error = "任务已由操作员取消"
	} else if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		result.Status = "failed"
		result.Error = "任务超过受控执行时限"
	} else if err := g.validateBinding(context.Background(), job.session, job.revision, job.lease); err != nil {
		result.Status = "failed"
		result.Error = "终态权威校验失败，结果不予采信"
		result.Notes = append(result.Notes, err.Error())
	}
	g.finishPerformance(job, result)
}

func (g *demoGuard) finishPerformance(job *demoJob, result RunResult) {
	job.cancel()
	if !g.release(job.session, job.lease) {
		result.Status = "failed"
		result.Error = "租约释放失败，权威栅栏仍保持"
	}
	result = g.sanitizeRunResult(result)
	result.Stage = "结果已归档"
	result.FinishedAt = time.Now().Format(time.RFC3339)
	if job.audit != nil {
		job.audit.Batch.Status, job.audit.Batch.FinishedAt = result.Status, result.FinishedAt
		if result.Error != "" {
			job.audit.Batch.Error = result.Error
		}
		if err := g.server.saveLifecycleAudit(*job.audit, job.auditRows); err != nil {
			result.Status = "failed"
			result.Error = "验收生命周期归档失败"
		}
	}
	g.mu.Lock()
	job.result = result
	g.mu.Unlock()
	close(job.done)
}

func (g *demoGuard) executeSecurity(ctx context.Context, job *demoSecurityJob) {
	result := job.result
	result.Status = "failed"
	result.Stage = "启动前核验"
	if err := g.validateBinding(ctx, job.session, job.revision, job.lease); err != nil {
		result.Error = "启动前权威校验失败: " + err.Error()
		g.finishSecurity(job, result)
		return
	}
	g.updateSecurityStage(job, "running", "执行固定安全用例")
	stopWatch, watchDone := g.watchBinding(ctx, job.session, job.revision, job.lease, job.cancel)
	executed := g.executeSecurityRun(ctx, job.result.CaseID)
	close(stopWatch)
	watchErr := <-watchDone
	result = g.sanitizeSecurityResult(executed)
	result.ID = job.result.ID
	result.CaseID = job.result.CaseID
	result.StartedAt = job.result.StartedAt
	result.Stage = "核验执行结果"
	if watchErr != nil {
		result.Status = "failed"
		result.Passed = false
		result.Error = "执行期间 Demo 权威失效，任务已终止"
		result.Notes = append(result.Notes, watchErr.Error())
	} else if errors.Is(ctx.Err(), context.Canceled) {
		result.Status = "cancelled"
		result.Passed = false
		result.Error = "任务已由操作员取消"
	} else if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		result.Status = "failed"
		result.Passed = false
		result.Error = "任务超过受控执行时限"
	} else if err := g.validateBinding(context.Background(), job.session, job.revision, job.lease); err != nil {
		result.Status = "failed"
		result.Passed = false
		result.Error = "终态权威校验失败，结果不予采信"
		result.Notes = append(result.Notes, err.Error())
	}
	g.finishSecurity(job, result)
}

func (g *demoGuard) finishSecurity(job *demoSecurityJob, result SecurityRunResult) {
	job.cancel()
	if !g.release(job.session, job.lease) {
		result.Status = "failed"
		result.Passed = false
		result.Error = "租约释放失败，权威栅栏仍保持"
	}
	result = g.sanitizeSecurityResult(result)
	result.Stage = "结果已归档"
	result.FinishedAt = time.Now().Format(time.RFC3339)
	g.mu.Lock()
	job.result = result
	g.mu.Unlock()
	close(job.done)
}

func (g *demoGuard) read(c *fiber.Ctx, session string, revision int64) error {
	if c.Path() == "/api/acceptance/lifecycle" || demoLifecyclePath.MatchString(c.Path()) {
		return g.readLifecycleAudit(c, session, revision)
	}
	switch c.Path() {
	case "/api/health":
		wrkPath, wrkAvailable := resolveExecutable(g.server.defaultWrkPath)
		securityAvailable := len(systemSecurityCases) > 0
		return c.JSON(fiber.Map{
			"status":                        "ok",
			"service":                       "kms-acceptance-backend",
			"wrkAvailable":                  wrkAvailable,
			"wrkPath":                       wrkPath,
			"securityAvailable":             securityAvailable,
			"securityExecutable":            "native-http-probes",
			"securityScriptPath":            "system_security.go",
			"scopedExecutionAvailable":      wrkAvailable || securityAvailable,
			"performanceExecutionAvailable": wrkAvailable,
			"securityExecutionAvailable":    securityAvailable,
			"executionUnavailableReason": func() string {
				if wrkAvailable || securityAvailable {
					return ""
				}
				return "wrk 与安全脚本均不可用"
			}(),
			"boundaryProbeAvailable": true,
		})
	case "/api/scenarios":
		list := []fiber.Map{{"id": boundaryProbeID, "name": "Demo 权威与入口边界探针", "description": "真实调用 ADMIN 权威与租约续期 RPC，校验本地固定路由白名单；不生成、更新或回收业务密钥，不代表业务 TPS 或端到端攻击验收。", "method": "POST", "path": "/runs", "durationSeconds": 3, "threads": 1, "connections": 1, "available": true, "headers": fiber.Map{}}}
		_, wrkAvailable := resolveExecutable(g.server.defaultWrkPath)
		for _, scenario := range g.server.scenarios {
			available := wrkAvailable && demoScenarioAllowed(scenario.ID)
			reason := ""
			if !available {
				reason = "wrk 不可用或场景未进入 Demo 白名单"
			}
			list = append(list, fiber.Map{"id": scenario.ID, "name": scenario.Name, "description": scenario.Description, "method": scenario.Method, "path": scenario.Path, "targetTps": scenario.TargetTPS, "available": available, "unavailableReason": reason, "headers": fiber.Map{}})
		}
		return c.JSON(fiber.Map{"data": list})
	case "/api/runs":
		g.mu.RLock()
		defer g.mu.RUnlock()
		list := []RunResult{}
		for i := len(g.jobOrder) - 1; i >= 0; i-- {
			job := g.jobs[g.jobOrder[i]]
			if job.session == session && job.revision == revision {
				list = append(list, job.result)
			}
		}
		return c.JSON(fiber.Map{"data": list})
	case "/api/acceptance/criteria":
		return c.Next()
	case "/api/acceptance/evidence":
		g.mu.RLock()
		defer g.mu.RUnlock()
		list := []fiber.Map{}
		for i := len(g.evidence) - 1; i >= 0; i-- {
			item := g.evidence[i]
			if item.session == session && item.revision == revision {
				list = append(list, item.payload)
			}
		}
		return c.JSON(fiber.Map{"data": list})
	case "/api/security/runs":
		g.mu.RLock()
		defer g.mu.RUnlock()
		list := []SecurityRunResult{}
		for i := len(g.securityJobOrder) - 1; i >= 0; i-- {
			job := g.securityJobs[g.securityJobOrder[i]]
			if job.session == session && job.revision == revision {
				list = append(list, job.result)
			}
		}
		return c.JSON(fiber.Map{"data": list})
	case "/api/proof/runs":
		// Old persisted records have no authoritative owner/revision and may contain
		// internal credentials in command output. Do not expose them to a new session.
		return c.JSON(fiber.Map{"data": []interface{}{}})
	default:
		if match := demoRunPath.FindStringSubmatch(c.Path()); len(match) > 0 {
			g.mu.RLock()
			defer g.mu.RUnlock()
			job := g.jobs[match[1]]
			if job == nil || job.session != session || job.revision != revision {
				return c.Status(404).JSON(fiber.Map{"message": "run not found"})
			}
			return c.JSON(job.result)
		}
		match := demoSecurityRunPath.FindStringSubmatch(c.Path())
		g.mu.RLock()
		defer g.mu.RUnlock()
		job := g.securityJobs[match[1]]
		if job == nil || job.session != session || job.revision != revision {
			return c.Status(404).JSON(fiber.Map{"message": "security run not found"})
		}
		return c.JSON(job.result)
	}
}

func (g *demoGuard) validate(ctx context.Context, job *demoJob) error {
	_, err := g.rpc(ctx, "lease/validate", map[string]interface{}{"sessionId": job.session, "leaseId": job.lease})
	return err
}

func (g *demoGuard) executeProbe(ctx context.Context, job *demoJob) {
	// This probe has no business side effects. Any future fixture/protocol runner
	// must use this existing lease, validate before every effect, and join all
	// workers before returning here; never call the legacy privileged handlers.
	status, message := "passed", "权威 ADMIN/版本、租约续期 RPC 与本地路由白名单校验通过；未写入业务数据，不代表业务 TPS 或端到端攻击验收。"
	for step := 0; step < 3; step++ {
		if err := g.validate(ctx, job); err != nil {
			status, message = "failed", "租约失效或权威不可用，已停止探针"
			break
		}
		data, err := g.rpc(ctx, "introspect", map[string]interface{}{"sessionId": job.session, "revision": job.revision})
		if err != nil || !adminIdentity(data, false, job.revision) {
			status, message = "failed", "当前任务身份已失效，已停止探针"
			break
		}
		if canonicalDemoRoute("POST", "/api/internal/generate") || canonicalDemoRoute("DELETE", "/api/runs") || canonicalDemoRoute("GET", "/api/runs/../health") {
			status, message = "failed", "固定路由边界校验失败"
			break
		}
		select {
		case <-ctx.Done():
			status, message = "cancelled", "探针已停止"
		case <-time.After(time.Second):
		}
		if ctx.Err() != nil {
			break
		}
	}
	if status == "passed" {
		if err := g.validate(ctx, job); err != nil {
			status, message = "failed", "终态权威租约校验失败，探针未通过"
		}
		if ctx.Err() != nil {
			status, message = "cancelled", "探针已停止"
		}
	}
	job.cancel()
	// There are no detached child workers or further business effects. Finish
	// release before publishing terminal state; failure never clears the fence.
	if !g.release(job.session, job.lease) {
		status, message = "failed", "租约释放失败，权威栅栏仍保持；不会盲目解除角色切换保护。"
	}
	g.mu.Lock()
	job.result.Status = status
	job.result.FinishedAt = time.Now().Format(time.RFC3339)
	job.result.Notes = []string{message}
	g.mu.Unlock()
	close(job.done)
}

func (g *demoGuard) cancelJob(c *fiber.Ctx, id, session string, revision int64) error {
	g.mu.RLock()
	job := g.jobs[id]
	g.mu.RUnlock()
	if job == nil || job.session != session || job.revision != revision {
		return c.Status(404).JSON(fiber.Map{"message": "run not found"})
	}
	select {
	case <-job.done:
		return c.JSON(fiber.Map{"status": "terminal"})
	default:
	}
	// CSRF was checked by introspect. Reuse the worker's lease, never acquire a
	// second mutually exclusive lease for cancellation.
	if err := g.validate(context.Background(), job); err != nil {
		job.cancel()
		return demoFailure(c, err)
	}
	job.cancel()
	select {
	case <-job.done:
		return c.JSON(fiber.Map{"status": "cancelled"})
	case <-time.After(6 * time.Second):
		return c.Status(503).JSON(fiber.Map{"message": "任务仍在停止；权威栅栏保持"})
	}
}

func (g *demoGuard) cancelSecurityJob(c *fiber.Ctx, id, session string, revision int64) error {
	g.mu.RLock()
	job := g.securityJobs[id]
	g.mu.RUnlock()
	if job == nil || job.session != session || job.revision != revision {
		return c.Status(404).JSON(fiber.Map{"message": "security run not found"})
	}
	select {
	case <-job.done:
		return c.JSON(fiber.Map{"status": "terminal"})
	default:
	}
	if err := g.validateBinding(context.Background(), job.session, job.revision, job.lease); err != nil {
		job.cancel()
		return demoFailure(c, err)
	}
	job.cancel()
	select {
	case <-job.done:
		return c.JSON(fiber.Map{"status": "cancelled"})
	case <-time.After(6 * time.Second):
		return c.Status(503).JSON(fiber.Map{"message": "安全任务仍在停止；权威栅栏保持"})
	}
}
