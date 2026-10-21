package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func abnormalFixture() *abnormalEvidence {
	e := &abnormalEvidence{Version: 2, Source: abnormalSource, Isolated: true, CleanupComplete: true, BatchID: "batch", BatchLimit: 5000,
		Batches: []abnormalBatch{{BatchID: "first", Attempted: 5000, Revoked: 5000, PoolRevoked: 5000, SessionsRevoked: 5000, ElapsedMs: 400},
			{BatchID: "second", Attempted: 1000, Revoked: 1000, PoolRevoked: 1000, SessionsRevoked: 1000, ElapsedMs: 100}},
		Injected: 6000, Attempted: 6000, Detected: 6000, Revoked: 6000, Controls: 4, ControlsPassed: 4, PoolRevoked: 6000,
		SessionsRevoked: 6000, Invalidations: 6000, ElapsedMs: 500, TotalMs: 1000, Passed: true,
		BeforeAt: "2026-10-21T16:00:00+08:00", ObservedAt: "2026-10-21T16:00:01+08:00"}
	for _, rule := range []string{"PUBLIC_KEY_MISSING", "PUBLIC_KEY_HASH_MISSING", "PUBLIC_KEY_HASH_MISMATCH"} {
		e.Rules = append(e.Rules, abnormalRule{Rule: rule})
	}
	for i := 0; i < 6000; i++ {
		rule := &e.Rules[i%3]
		rule.Injected++
		rule.Detected++
		rule.Revoked++
		e.Rows = append(e.Rows, abnormalRow{KeyID: int64(i + 1), NodeID: "isolated-node", Algorithm: "KYBER",
			Rule: rule.Rule, DetectedRule: rule.Rule, Abnormal: true, Attempted: true, BeforeStatus: "ACTIVE", AfterStatus: "REVOKED", Action: "AUTO_REVOKED", Passed: true})
	}
	for i := 0; i < 4; i++ {
		row := abnormalRow{KeyID: int64(6001 + i), NodeID: "isolated-control", Algorithm: "KYBER", BeforeStatus: "ACTIVE", AfterStatus: "ACTIVE", Passed: true}
		if i == 3 {
			row.Rule = "MATERIALIZED_PUBLIC_KEY_MISMATCH"
			row.DetectedRule = row.Rule
			row.Action = "PENDING_REVIEW"
		}
		e.Rows = append(e.Rows, row)
	}
	return e
}

func TestAbnormalEvidenceRequiresRealFixedAnomalyAndControlSnapshots(t *testing.T) {
	if err := validateAbnormalEvidence(abnormalFixture()); err != nil {
		t.Fatal(err)
	}
	mutations := map[string]func(*abnormalEvidence){
		"no cleanup":              func(e *abnormalEvidence) { e.CleanupComplete = false },
		"no isolation":            func(e *abnormalEvidence) { e.Isolated = false },
		"no samples":              func(e *abnormalEvidence) { e.Rows = nil },
		"duplicate snapshot":      func(e *abnormalEvidence) { e.Rows[1].KeyID = e.Rows[0].KeyID },
		"missing rule":            func(e *abnormalEvidence) { e.Rules = e.Rules[1:] },
		"false detection":         func(e *abnormalEvidence) { e.Rows[0].DetectedRule = "" },
		"false pass":              func(e *abnormalEvidence) { e.Rows[0].AfterStatus = "ACTIVE" },
		"miscount":                func(e *abnormalEvidence) { e.Detected-- },
		"zero timer":              func(e *abnormalEvidence) { e.ElapsedMs = 0 },
		"missing warning control": func(e *abnormalEvidence) { e.Rows[6003].Rule = "" },
		"old sample contract":     func(e *abnormalEvidence) { e.Version = 1 },
		"missing second batch":    func(e *abnormalEvidence) { e.Batches = e.Batches[:1] },
		"duplicate batch":         func(e *abnormalEvidence) { e.Batches[1].BatchID = e.Batches[0].BatchID },
		"false batch count":       func(e *abnormalEvidence) { e.Batches[1].Revoked-- },
		"false attempted count":   func(e *abnormalEvidence) { e.Attempted-- },
		"success without attempt": func(e *abnormalEvidence) { e.Rows[0].Attempted = false },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			e := abnormalFixture()
			mutate(e)
			if validateAbnormalEvidence(e) == nil {
				t.Fatal("invalid evidence accepted")
			}
		})
	}
}

func abnormalRPC(t *testing.T, e *abnormalEvidence) *httptest.Server {
	t.Helper()
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.Header.Get("X-Internal-Token") != "server-secret" {
			t.Error("missing fixed internal authorization")
			w.WriteHeader(403)
			return
		}
		var body map[string]interface{}
		_ = json.NewDecoder(r.Body).Decode(&body)
		if len(body) != 0 {
			t.Error("client supplied execution parameters")
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": e})
	}))
	t.Cleanup(rpc.Close)
	return rpc
}

func TestAbnormalRunUsesMeasuredRevocationsAndRequiresControlsAndDependencies(t *testing.T) {
	for _, mode := range []string{"passed", "slow", "control-failed", "dependency-missing"} {
		t.Run(mode, func(t *testing.T) {
			e := abnormalFixture()
			switch mode {
			case "slow":
				e.ElapsedMs = 2000
				e.TotalMs = 2500
			case "control-failed":
				e.Rows[6000].AfterStatus = "REVOKED"
				e.Rows[6000].Passed = false
				e.ControlsPassed--
				e.Passed = false
			case "dependency-missing":
				e.Invalidations--
				e.Passed = false
			}
			rpc := abnormalRPC(t, e)
			s := &server{client: rpc.Client(), cfg: acceptanceConfig{AbnormalRevocationURL: rpc.URL, GenerateInternalToken: "server-secret"}}
			result := s.executeRun(context.Background(), "missing-wrk", Scenario{ID: "revoke-tps", TargetTPS: 5000, TargetOperator: ">="})
			if mode == "passed" {
				if result.Status != "passed" || result.Summary.SuccessfulRequestsPerSec != 12000 {
					t.Fatalf("bad result %+v", result)
				}
			} else if result.Status != "failed_threshold" {
				t.Fatalf("%s accepted: %+v", mode, result)
			}
			if !result.MetricCheck.Enforced || !result.MetricCheck.Collected {
				t.Fatal("closure evidence omitted")
			}
		})
	}
}

func TestAbnormalDemoNeedsNoWrkAndArchivesScopedSnapshots(t *testing.T) {
	app, guard, _ := demoTestApp(t)
	rpc := abnormalRPC(t, abnormalFixture())
	guard.server.cfg.AbnormalRevocationURL = rpc.URL
	guard.server.dataDir = t.TempDir()
	guard.server.defaultWrkPath = "no-such-wrk"
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"revoke-tps"}`))
	if status != 202 {
		t.Fatalf("%d %s", status, body)
	}
	var run RunResult
	_ = json.Unmarshal([]byte(body), &run)
	guard.mu.RLock()
	job := guard.jobs[run.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	case <-time.After(8 * time.Second):
		t.Fatal("native run did not finish")
	}
	if job.result.Status != "passed" || job.result.Abnormal == nil {
		t.Fatalf("native demo failed: %+v", job.result)
	}
	if len(job.result.Abnormal.Rows) != 0 {
		t.Fatal("unpaginated snapshots leaked into history")
	}
	status, body = demoResponse(t, app, demoRequest("GET", "/api/acceptance/lifecycle/"+run.ID+"?pageSize=20&outcome=CONTROL_PASSED", ""))
	if status != 200 || !strings.Contains(body, `"total":4`) || !strings.Contains(body, "MATERIALIZED_PUBLIC_KEY_MISMATCH") {
		t.Fatalf("missing control archive: %d %s", status, body)
	}
	foreign := demoRequest("GET", "/api/acceptance/lifecycle/"+run.ID, "")
	foreign.Header.Set("Cookie", "KMS-Demo-Session=foreign")
	status, _ = demoResponse(t, app, foreign)
	if status != 404 {
		t.Fatal("cross-session archive disclosed")
	}
}

// Boundary evidence is synthetic test input; live runs always use the scanner's actual counts.
func abnormalResults(attempted, succeeded int) *abnormalEvidence {
	e := abnormalFixture()
	for i := succeeded; i < e.Injected; i++ {
		e.Rows[i].AfterStatus, e.Rows[i].Action, e.Rows[i].Passed = "ACTIVE", "PENDING_REVIEW", false
		e.Rules[i%3].Revoked--
		if i >= attempted {
			e.Rows[i].Attempted, e.Rows[i].DetectedRule, e.Rows[i].Action = false, "", ""
			e.Rules[i%3].Detected--
		}
	}
	e.Attempted, e.Detected = attempted, attempted
	e.Revoked, e.PoolRevoked, e.SessionsRevoked, e.Invalidations = succeeded, succeeded, succeeded, succeeded
	for i := range e.Batches {
		batch := &e.Batches[i]
		batch.Attempted = max(0, min(5000, attempted-i*5000))
		batch.Revoked = max(0, min(5000, succeeded-i*5000))
		batch.PoolRevoked, batch.SessionsRevoked = batch.Revoked, batch.Revoked
	}
	e.Passed = succeeded == e.Injected
	return e
}

func TestAbnormalRecoveryPercentageIncludesUnrecoveredAndDoesNotRequireThroughput(t *testing.T) {
	for _, counts := range [][2]int{{4000, 3500}, {4000, 3919}, {4000, 3920}, {4000, 4000}, {6000, 5879}, {6000, 5880}, {6000, 6000}} {
		t.Run(fmt.Sprint(counts), func(t *testing.T) {
			attempted, count := counts[0], counts[1]
			e := abnormalResults(attempted, count)
			e.ElapsedMs, e.TotalMs = 2000, 2500 // Below 5000 keys/s even when all keys are recovered.
			rpc := abnormalRPC(t, e)
			s := &server{client: rpc.Client(), cfg: acceptanceConfig{AbnormalRevocationURL: rpc.URL, GenerateInternalToken: "server-secret"}}
			scenario := defaultScenarios(s.cfg)["revoke-rate"]
			result := s.executeRun(context.Background(), "missing-wrk", scenario)
			want := float64(count) * 100 / float64(attempted)
			if result.Error != "" || result.MetricCheck.Value != want || result.MetricCheck.Target != 98 || result.MetricCheck.Operator != ">=" ||
				result.MetricCheck.Passed != (want >= 98) || (result.Status == "passed") != (want >= 98) {
				t.Fatalf("bad recovery rate: %+v", result)
			}
			run := RunResult{ID: "run-20261021-170000-0001", ScenarioID: scenario.ID}
			archive, rows := abnormalAudit(run, e, "test-session", 1)
			if archive.Batch.ScenarioID != "revoke-rate" || archive.Batch.Eligible != attempted || archive.Batch.Excluded != 4 ||
				archive.Batch.NotAttempted != 6000-attempted || archive.Batch.Pending != attempted-count || *archive.Batch.CompletionRate != want || len(rows) != 6004 {
				t.Fatal("unrecovered keys or controls incorrectly counted")
			}
			applied := applyLifecycleAuditResult(scenario, archive, result)
			if applied.MetricCheck.Kind != "abnormal_revoke_rate" || applied.Status != result.Status {
				t.Fatal("legacy lifecycle check overrode abnormal evidence")
			}
		})
	}
}

func TestAbnormalRecoveryPercentageWithoutAttemptsIsUnavailable(t *testing.T) {
	e := abnormalResults(0, 0)
	rpc := abnormalRPC(t, e)
	s := &server{client: rpc.Client(), cfg: acceptanceConfig{AbnormalRevocationURL: rpc.URL, GenerateInternalToken: "server-secret"}}
	result := s.executeRun(context.Background(), "", defaultScenarios(s.cfg)["revoke-rate"])
	if result.Error == "" || result.MetricCheck.Collected || result.Status == "passed" {
		t.Fatalf("empty denominator accepted: %+v", result)
	}
	archive, _ := abnormalAudit(RunResult{ScenarioID: "revoke-rate"}, e, "session", 1)
	if archive.Batch.CompletionRate != nil {
		t.Fatal("empty denominator shown as a measured percentage")
	}
}

func TestAbnormalRecoveryPercentageRejectsControlOrDependencyFailures(t *testing.T) {
	for _, mode := range []string{"control", "dependency"} {
		t.Run(mode, func(t *testing.T) {
			e := abnormalFixture()
			e.Passed = false
			if mode == "control" {
				e.Rows[6000].AfterStatus, e.Rows[6000].Passed = "REVOKED", false
				e.ControlsPassed--
			} else {
				e.Invalidations--
			}
			rpc := abnormalRPC(t, e)
			s := &server{client: rpc.Client(), cfg: acceptanceConfig{AbnormalRevocationURL: rpc.URL, GenerateInternalToken: "server-secret"}}
			result := s.executeRun(context.Background(), "", defaultScenarios(s.cfg)["revoke-rate"])
			if result.Status != "failed_threshold" || result.MetricCheck.Passed || result.MetricCheck.Value != 100 {
				t.Fatalf("bad closure accepted: %+v", result)
			}
		})
	}
}

func TestAbnormalRecoveryRateDemoUsesIsolatedSamplesAndOwnArchive(t *testing.T) {
	app, guard, _ := demoTestApp(t)
	rpc := abnormalRPC(t, abnormalFixture())
	guard.server.cfg.AbnormalRevocationURL = rpc.URL
	guard.server.dataDir = t.TempDir()
	guard.server.defaultWrkPath = "no-such-wrk"
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"revoke-rate"}`))
	if status != 202 {
		t.Fatalf("%d %s", status, body)
	}
	var run RunResult
	_ = json.Unmarshal([]byte(body), &run)
	guard.mu.RLock()
	job := guard.jobs[run.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	case <-time.After(8 * time.Second):
		t.Fatal("recovery rate did not finish")
	}
	if job.result.Status != "passed" || job.result.MetricCheck.Value != 100 || job.result.MetricCheck.Target != 98 || job.result.MetricCheck.Operator != ">=" {
		t.Fatalf("bad rate: %+v", job.result)
	}
	status, body = demoResponse(t, app, demoRequest("GET", "/api/acceptance/lifecycle/"+run.ID+"?outcome=CONTROL_PASSED", ""))
	if status != 200 || !strings.Contains(body, `"scenarioId":"revoke-rate"`) || !strings.Contains(body, `"total":4`) ||
		!strings.Contains(body, `"eligible":6000`) || !strings.Contains(body, abnormalSource) {
		t.Fatalf("bad recovery rate archive: %d %s", status, body)
	}
}

func TestAbnormalRealMySQLEvidenceWhenProvided(t *testing.T) {
	file := os.Getenv("KMS_ACCEPTANCE_MYSQL_EVIDENCE")
	if file == "" {
		t.Skip("opt-in real MySQL evidence")
	}
	data, err := os.ReadFile(file)
	if err != nil {
		t.Fatal(err)
	}
	var envelope struct {
		Data *abnormalEvidence `json:"data"`
	}
	if err = json.Unmarshal(data, &envelope); err != nil {
		t.Fatal(err)
	}
	if err = validateAbnormalEvidence(envelope.Data); err != nil {
		t.Fatal(err)
	}
	rpc := abnormalRPC(t, envelope.Data)
	s := &server{client: rpc.Client(), cfg: acceptanceConfig{AbnormalRevocationURL: rpc.URL, GenerateInternalToken: "server-secret"}}
	r := s.executeRun(context.Background(), "", Scenario{ID: "revoke-tps", TargetTPS: 5000, TargetOperator: ">="})
	if r.Error != "" || r.Abnormal == nil || !r.MetricCheck.Passed {
		t.Fatal(fmt.Sprintf("real evidence rejected: %+v", r))
	}
}
