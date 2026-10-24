package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
)

type demoAuthorityMock struct {
	mu        sync.Mutex
	leased    bool
	revision  int64
	role      string
	acquires  int
	validates int
	releases  int
	fail      bool
	lost      bool
}

func (a *demoAuthorityMock) switchRevision() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.leased {
		return false
	}
	a.revision++
	return true
}

func (a *demoAuthorityMock) serve(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if r.Header.Get("X-Internal-Token") != "server-secret" {
		w.WriteHeader(403)
		return
	}
	if a.fail {
		w.WriteHeader(503)
		return
	}
	var payload map[string]interface{}
	_ = json.NewDecoder(r.Body).Decode(&payload)
	result := map[string]interface{}{"ok": true}
	identity := map[string]interface{}{"ok": true, "entryMode": "DEMO", "principalType": a.role, "userId": -1, "sessionRevision": a.revision}
	switch {
	case strings.HasSuffix(r.URL.Path, "introspect"):
		if payload["revision"] != float64(a.revision) {
			result = map[string]interface{}{"ok": false, "errorCode": "DEMO_REVISION_STALE"}
		} else if csrf, exists := payload["csrfToken"]; exists && csrf != "csrf" {
			result = map[string]interface{}{"ok": false, "errorCode": "DEMO_CSRF_INVALID"}
		} else {
			result = identity
		}
	case strings.HasSuffix(r.URL.Path, "lease/acquire"):
		if a.leased {
			result = map[string]interface{}{"ok": false, "errorCode": "DEMO_SESSION_BUSY"}
		} else if payload["csrfToken"] != "csrf" || payload["revision"] != float64(a.revision) {
			result = map[string]interface{}{"ok": false}
		} else {
			a.leased = true
			a.acquires++
			result["leaseId"] = "lease"
			result["identity"] = identity
		}
	case strings.HasSuffix(r.URL.Path, "lease/validate"):
		a.validates++
		result["ok"] = a.leased && !a.lost && payload["leaseId"] == "lease"
	case strings.HasSuffix(r.URL.Path, "lease/release"):
		if payload["leaseId"] == "lease" {
			a.leased = false
			a.releases++
		}
	default:
		w.WriteHeader(404)
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": result})
}

func demoTestApp(t *testing.T) (*fiber.App, *demoGuard, *demoAuthorityMock) {
	t.Helper()
	authority := &demoAuthorityMock{revision: 1, role: "ADMIN"}
	rpc := httptest.NewServer(http.HandlerFunc(authority.serve))
	t.Cleanup(rpc.Close)
	s := &server{client: rpc.Client(), cfg: acceptanceConfig{GenerateInternalToken: "server-secret"}, scenarios: defaultScenarios(acceptanceConfig{GenerateInternalToken: "private-must-not-leak"})}
	s.acceptanceEvidence = map[string]*AcceptanceEvidence{}
	s.acceptanceEvidenceFile = filepath.Join(t.TempDir(), "evidence.json")
	guard := newDemoGuard(s)
	guard.enabled = true
	guard.token = "server-secret"
	guard.authority = rpc.URL + "/"
	guard.hosts = map[string]bool{"127.0.0.1:8088": true}
	guard.origins = map[string]bool{"http://127.0.0.1:8088": true}
	app := fiber.New()
	app.Use(guard.authorize)
	app.Get("/api/acceptance/criteria", s.handleAcceptanceCriteria)
	app.Post("/api/acceptance/evidence", s.handleCreateAcceptanceEvidence)
	t.Cleanup(func() {
		guard.mu.RLock()
		jobs := []*demoJob{}
		for _, job := range guard.jobs {
			job.cancel()
			jobs = append(jobs, job)
		}
		guard.mu.RUnlock()
		for _, job := range jobs {
			select {
			case <-job.done:
			case <-time.After(8 * time.Second):
				t.Error("worker did not stop")
			}
		}
		securityJobs := []*demoSecurityJob{}
		guard.mu.RLock()
		for _, job := range guard.securityJobs {
			job.cancel()
			securityJobs = append(securityJobs, job)
		}
		guard.mu.RUnlock()
		for _, job := range securityJobs {
			select {
			case <-job.done:
			case <-time.After(8 * time.Second):
				t.Error("security worker did not stop")
			}
		}
	})
	return app, guard, authority
}

func demoRequest(method, path, body string) *http.Request {
	req := httptest.NewRequest(method, "http://127.0.0.1:8088"+path, strings.NewReader(body))
	req.RequestURI = path // Browser/nginx uses origin-form, not proxy absolute-form.
	req.Header.Set("X-Kms-Demo-Gateway", "server-secret")
	req.Header.Set("X-Kms-Entry-Mode", "demo")
	req.Header.Set("Cookie", "KMS-Demo-Session=owner")
	req.Header.Set("X-Kms-Demo-Revision", "1")
	req.Header.Set("Content-Type", "application/json")
	if method == "POST" {
		req.Header.Set("Origin", "http://127.0.0.1:8088")
		req.Header.Set("X-Kms-Demo-CSRF", "csrf")
	}
	return req
}

func demoResponse(t *testing.T, app *fiber.App, req *http.Request) (int, string) {
	t.Helper()
	resp, err := app.Test(req, 10000)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	return resp.StatusCode, string(body)
}

func TestDemoIngressAndCanonicalRoutes(t *testing.T) {
	app, _, authority := demoTestApp(t)
	cases := []struct {
		name, method, path string
		status             int
		change             func(*http.Request)
	}{
		{"direct", "GET", "/api/health", 404, func(r *http.Request) { r.Header.Del("X-Kms-Demo-Gateway") }},
		{"forged", "GET", "/api/health", 404, func(r *http.Request) { r.Header.Set("X-Kms-Demo-Gateway", "wrong") }},
		{"host", "GET", "/api/health", 404, func(r *http.Request) { r.Host = "evil.example" }},
		{"origin", "POST", "/api/runs", 403, func(r *http.Request) { r.Header.Set("Origin", "https://evil.example") }},
		{"read origin", "GET", "/api/health", 403, func(r *http.Request) { r.Header.Set("Origin", "https://evil.example") }},
		{"entry", "GET", "/api/health", 404, func(r *http.Request) { r.Header.Set("X-Kms-Entry-Mode", "standalone") }},
		{"internal browser auth", "GET", "/api/health", 404, func(r *http.Request) { r.Header.Set("X-Internal-Token", "server-secret") }},
		{"bearer", "GET", "/api/health", 404, func(r *http.Request) { r.Header.Set("Authorization", "Bearer fake") }},
		{"missing cookie", "GET", "/api/health", 401, func(r *http.Request) { r.Header.Del("Cookie") }},
		{"duplicate cookie", "GET", "/api/health", 401, func(r *http.Request) { r.Header.Set("Cookie", "KMS-Demo-Session=owner; KMS-Demo-Session=other") }},
		{"stale", "GET", "/api/health", 409, func(r *http.Request) { r.Header.Set("X-Kms-Demo-Revision", "0") }},
		{"missing csrf", "POST", "/api/runs", 403, func(r *http.Request) { r.Header.Del("X-Kms-Demo-CSRF") }},
		{"bad csrf", "POST", "/api/runs", 409, func(r *http.Request) { r.Header.Set("X-Kms-Demo-CSRF", "wrong") }},
		{"encoded", "GET", "/api/%68ealth", 404, nil},
		{"unknown method", "DELETE", "/api/runs", 404, nil},
		{"unknown route", "POST", "/api/internal/generate", 404, nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := demoRequest(tc.method, tc.path, `{"scenarioId":"demo-boundary-probe"}`)
			if tc.change != nil {
				tc.change(req)
			}
			status, _ := demoResponse(t, app, req)
			if status != tc.status {
				t.Fatalf("status=%d want=%d", status, tc.status)
			}
		})
	}
	authority.mu.Lock()
	defer authority.mu.Unlock()
	if authority.acquires != 0 {
		t.Fatal("invalid requests acquired lease")
	}
}

func TestDemoRoleAuthorityFailuresAndSafeCapabilities(t *testing.T) {
	app, guard, authority := demoTestApp(t)
	status, body := demoResponse(t, app, demoRequest("GET", "/api/scenarios", ""))
	if status != 200 || strings.Contains(body, "private-must-not-leak") || !strings.Contains(body, `"available":false`) || !strings.Contains(body, boundaryProbeID) {
		t.Fatalf("unsafe scenarios %d %s", status, body)
	}
	// Legacy wrk-only scenarios still reject startup when the binary is absent.
	legacy := guard.server.scenarios["generate-tps"]
	legacy.ID = "wrk-only-test"
	guard.server.scenarios["generate-tps"] = legacy
	status, _ = demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"generate-tps"}`))
	if status != 503 {
		t.Fatalf("legacy start status=%d", status)
	}
	authority.mu.Lock()
	if authority.leased || authority.acquires != 1 || authority.releases != 1 {
		t.Fatal("unavailable start leaked lease")
	}
	authority.role = "NODE"
	authority.mu.Unlock()
	status, _ = demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"demo-boundary-probe"}`))
	if status != 403 {
		t.Fatalf("node start status=%d", status)
	}
	authority.mu.Lock()
	authority.role = "ADMIN"
	authority.fail = true
	authority.mu.Unlock()
	status, _ = demoResponse(t, app, demoRequest("GET", "/api/health", ""))
	if status != 503 {
		t.Fatalf("authority failure status=%d", status)
	}
}

func TestDemoAsyncLeaseOwnershipStatusCancelAndSwitchFence(t *testing.T) {
	app, guard, authority := demoTestApp(t)
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"demo-boundary-probe"}`))
	if status != 202 {
		t.Fatalf("start %d %s", status, body)
	}
	var result RunResult
	if json.Unmarshal([]byte(body), &result) != nil {
		t.Fatal(body)
	}
	authority.mu.Lock()
	if !authority.leased || authority.releases != 0 {
		t.Fatal("202 released lease / would permit role switch")
	}
	authority.mu.Unlock()
	if authority.switchRevision() {
		t.Fatal("role switch crossed inflight fence")
	}
	status, _ = demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"demo-boundary-probe"}`))
	if status != 409 {
		t.Fatalf("concurrent start=%d", status)
	}
	status, _ = demoResponse(t, app, demoRequest("GET", "/api/runs/"+result.ID, ""))
	if status != 200 {
		t.Fatalf("owned status=%d", status)
	}
	req := demoRequest("GET", "/api/runs/"+result.ID, "")
	req.Header.Set("Cookie", "KMS-Demo-Session=other")
	status, _ = demoResponse(t, app, req)
	if status != 404 {
		t.Fatalf("foreign status=%d", status)
	}
	req = demoRequest("POST", "/api/runs/"+result.ID+"/cancel", "{}")
	req.Header.Set("X-Kms-Demo-CSRF", "bad")
	status, _ = demoResponse(t, app, req)
	if status != 409 {
		t.Fatalf("bad csrf cancel=%d", status)
	}
	req = demoRequest("POST", "/api/runs/"+result.ID+"/cancel", "{}")
	req.Header.Set("Cookie", "KMS-Demo-Session=other")
	status, _ = demoResponse(t, app, req)
	if status != 404 {
		t.Fatalf("foreign cancel=%d", status)
	}
	status, _ = demoResponse(t, app, demoRequest("POST", "/api/runs/"+result.ID+"/cancel", "{}"))
	if status != 200 {
		t.Fatalf("cancel=%d", status)
	}
	guard.mu.RLock()
	job := guard.jobs[result.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	default:
		t.Fatal("cancel returned before worker joined")
	}
	authority.mu.Lock()
	if authority.leased || authority.acquires != 1 || authority.releases != 1 {
		t.Fatalf("cancel acquired another mutex or release count incorrect")
	}
	authority.mu.Unlock()
	if !authority.switchRevision() {
		t.Fatal("joined cancellation did not release role switch fence")
	}
	status, _ = demoResponse(t, app, demoRequest("GET", "/api/runs/"+result.ID, ""))
	if status != 409 {
		t.Fatalf("old revision status=%d", status)
	}
}

func TestDemoBoundaryProbeCompletesRealAuthorityChecksWithoutTPSClaim(t *testing.T) {
	app, guard, authority := demoTestApp(t)
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"demo-boundary-probe"}`))
	if status != 202 {
		t.Fatal(body)
	}
	var started RunResult
	_ = json.Unmarshal([]byte(body), &started)
	guard.mu.RLock()
	job := guard.jobs[started.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	case <-time.After(8 * time.Second):
		t.Fatal("bounded probe did not complete")
	}
	guard.mu.RLock()
	result := job.result
	guard.mu.RUnlock()
	if result.Status != "passed" || result.PassedTPS || result.Summary.TotalRequests != 0 || len(result.Notes) == 0 {
		t.Fatalf("probe fabricated performance evidence: %#v", result)
	}
	authority.mu.Lock()
	validates, releases, leased := authority.validates, authority.releases, authority.leased
	authority.mu.Unlock()
	if validates < 3 || releases != 1 || leased {
		t.Fatal("probe did not validate throughout and release at terminal")
	}
}

func TestDemoProbeLostAuthorityStopsAndDoesNotBlindUnlock(t *testing.T) {
	app, guard, authority := demoTestApp(t)
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"demo-boundary-probe"}`))
	if status != 202 {
		t.Fatal(body)
	}
	var result RunResult
	_ = json.Unmarshal([]byte(body), &result)
	authority.mu.Lock()
	authority.fail = true
	authority.mu.Unlock()
	guard.mu.RLock()
	job := guard.jobs[result.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	case <-time.After(8 * time.Second):
		t.Fatal("worker failed to stop")
	}
	guard.mu.RLock()
	final := job.result
	guard.mu.RUnlock()
	if final.Status != "failed" {
		t.Fatalf("status=%s", final.Status)
	}
	authority.mu.Lock()
	defer authority.mu.Unlock()
	if !authority.leased || authority.releases != 0 {
		t.Fatal("failed authority was blindly unlocked")
	}
}

func TestDemoManualEvidenceIsLeasedOwnedAndNeverAutomaticSuccess(t *testing.T) {
	app, _, authority := demoTestApp(t)
	body := `{"criterionId":"preallocation","value":100,"evidence":"fixture-local measurement"}`
	status, response := demoResponse(t, app, demoRequest("POST", "/api/acceptance/evidence", body))
	if status != 200 || !strings.Contains(response, `"verified":false`) || !strings.Contains(response, `"passed":false`) || !strings.Contains(response, `"thresholdMet":true`) {
		t.Fatalf("manual claim became verified or record failed: %d %s", status, response)
	}
	authority.mu.Lock()
	if authority.acquires != 1 || authority.validates != 1 || authority.releases != 1 || authority.leased {
		t.Fatal("evidence write did not hold validated lease until completion")
	}
	authority.mu.Unlock()
	status, response = demoResponse(t, app, demoRequest("GET", "/api/acceptance/evidence", ""))
	if status != 200 || !strings.Contains(response, "fixture-local") {
		t.Fatal("owner lost evidence")
	}
	req := demoRequest("GET", "/api/acceptance/evidence", "")
	req.Header.Set("Cookie", "KMS-Demo-Session=other")
	_, response = demoResponse(t, app, req)
	if strings.Contains(response, "fixture-local") {
		t.Fatal("foreign session read evidence")
	}
	req = demoRequest("POST", "/api/acceptance/evidence", body)
	req.Header.Set("X-Kms-Demo-CSRF", "bad")
	status, _ = demoResponse(t, app, req)
	if status != 409 {
		t.Fatalf("bad CSRF evidence=%d", status)
	}
	authority.mu.Lock()
	authority.lost = true
	authority.mu.Unlock()
	status, _ = demoResponse(t, app, demoRequest("POST", "/api/acceptance/evidence", body))
	if status != 409 {
		t.Fatalf("lost lease evidence=%d", status)
	}
}

func TestDemoNoOverridesOrLegacyProofSecurityExecution(t *testing.T) {
	app, _, authority := demoTestApp(t)
	for _, body := range []string{`{"scenarioId":"demo-boundary-probe","baseUrl":"http://evil"}`, `{"scenarioId":"demo-boundary-probe","wrkPath":"evil"}`, `{"scenarioId":"demo-boundary-probe","body":"private"}`, `{"scenarioId":"demo-boundary-probe"} {}`} {
		status, _ := demoResponse(t, app, demoRequest("POST", "/api/runs", body))
		if status != 400 {
			t.Fatalf("override status=%d", status)
		}
	}
	status, response := demoResponse(t, app, demoRequest("POST", "/api/security/runs", `{}`))
	if status != 400 {
		t.Fatalf("empty security case=%d %s", status, response)
	}
	status, response = demoResponse(t, app, demoRequest("POST", "/api/security/runs", `{"caseId":"algo-tamper","command":"evil"}`))
	if status != 400 {
		t.Fatalf("security override=%d %s", status, response)
	}
	status, response = demoResponse(t, app, demoRequest("POST", "/api/proof/runs", `{}`))
	if status != 503 {
		t.Fatalf("unsafe proof start=%d %s", status, response)
	}
	authority.mu.Lock()
	defer authority.mu.Unlock()
	if authority.leased || authority.acquires != authority.releases {
		t.Fatal("rejected command leaked a lease")
	}
}

func TestDemoFixedPerformanceAndSecurityJobsExecuteAndStaySessionScoped(t *testing.T) {
	app, guard, authority := demoTestApp(t)
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	guard.server.defaultWrkPath = executable
	guard.server.bashPath = "fixed-bash"
	guard.server.securityScript = "fixed-security-script"
	guard.executeRun = func(ctx context.Context, _ string, scenario Scenario) RunResult {
		if scenario.ID != "generate-tps" || scenario.BaseURL == "" || scenario.Headers["X-Internal-Token"] == "" {
			return RunResult{Status: "failed", Error: "fixed scenario missing"}
		}
		return RunResult{Status: "passed", PassedTPS: true, Summary: RunSummary{SuccessfulRequestsPerSec: 120001, RawOutput: "token=private-must-not-leak"}}
	}
	guard.executeSecurityRun = func(ctx context.Context, caseID string) SecurityRunResult {
		return SecurityRunResult{CaseID: caseID, Status: "passed", Verdict: "blocked", Passed: true, Summary: "固定攻击载荷已被拒绝", RawOutput: "secret=server-secret"}
	}

	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"generate-tps"}`))
	if status != 202 {
		t.Fatalf("performance start=%d %s", status, body)
	}
	var started RunResult
	if err := json.Unmarshal([]byte(body), &started); err != nil {
		t.Fatal(err)
	}
	guard.mu.RLock()
	job := guard.jobs[started.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	case <-time.After(3 * time.Second):
		t.Fatal("performance job did not finish")
	}
	guard.mu.RLock()
	performance := job.result
	guard.mu.RUnlock()
	if performance.Status != "passed" || !performance.PassedTPS || strings.Contains(performance.Summary.RawOutput, "private-must-not-leak") || len(performance.WrkCommand) != 0 {
		t.Fatalf("unsafe performance result %#v", performance)
	}
	wantStages := []string{"核验操作权限与测试会话", "准备固定性能场景与验收数据", "记录验收密钥初始状态", "执行固定性能场景", "核验最终状态并归档测量证据", "结果已归档"}
	if len(performance.Stages) != len(wantStages) {
		t.Fatalf("missing execution history: %#v", performance.Stages)
	}
	for index, stage := range performance.Stages {
		if stage.Label != wantStages[index] || stage.At == "" {
			t.Fatalf("invalid stage %d: %#v", index, stage)
		}
	}

	status, body = demoResponse(t, app, demoRequest("POST", "/api/security/runs", `{"caseId":"generation-identity-injection"}`))
	if status != 202 {
		t.Fatalf("security start=%d %s", status, body)
	}
	var securityStarted SecurityRunResult
	if err := json.Unmarshal([]byte(body), &securityStarted); err != nil {
		t.Fatal(err)
	}
	guard.mu.RLock()
	securityJob := guard.securityJobs[securityStarted.ID]
	guard.mu.RUnlock()
	select {
	case <-securityJob.done:
	case <-time.After(3 * time.Second):
		t.Fatal("security job did not finish")
	}
	guard.mu.RLock()
	security := securityJob.result
	guard.mu.RUnlock()
	if security.Status != "passed" || !security.Passed || strings.Contains(security.RawOutput, "server-secret") {
		t.Fatalf("unsafe security result %#v", security)
	}

	req := demoRequest("GET", "/api/security/runs", "")
	req.Header.Set("Cookie", "KMS-Demo-Session=other")
	_, body = demoResponse(t, app, req)
	if strings.Contains(body, security.ID) {
		t.Fatal("security result leaked across sessions")
	}
	authority.mu.Lock()
	defer authority.mu.Unlock()
	if authority.acquires != 2 || authority.releases != 2 || authority.leased {
		t.Fatalf("jobs did not hold and release leases: %#v", authority)
	}
}
