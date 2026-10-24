package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestSymmetricRealMySQLEvidence(t *testing.T) {
	path := os.Getenv("KMS_SYMMETRIC_EVIDENCE")
	if path == "" {
		t.Skip("optional real MySQL evidence")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var envelope struct {
		Code int                `json:"code"`
		Data *symmetricEvidence `json:"data"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		t.Fatal(err)
	}
	if envelope.Code != 200 {
		t.Fatal("evidence envelope failed")
	}
	if err := validateSymmetricEvidence(envelope.Data); err != nil {
		t.Fatal(err)
	}
}

func symmetricFixture() *symmetricEvidence {
	e := &symmetricEvidence{Version: 1, Source: symmetricSource, Isolated: true, CleanupComplete: true, MaterialVerified: true,
		BatchID: "test", Injected: symmetricCount, Reclaimed: symmetricCount, Controls: 4, ControlsPassed: 4,
		ElapsedMs: 1200, TotalMs: 5000, BeforeAt: "2026-10-22T10:00:00Z", ObservedAt: "2026-10-22T10:00:02Z", Passed: true}
	for i := 0; i < symmetricCount+4; i++ {
		hash := sha256.Sum256([]byte(fmt.Sprint(i)))
		row := symmetricRow{KeyID: int64(i + 1), PoolID: "test-pool", KeyIndex: i, KeyHash: fmt.Sprintf("%x", hash),
			Algorithm: "sm4", Eligible: i < symmetricCount, ExpiresAt: "2026-10-22T09:00:00Z", BeforeStatus: []string{"READY", "EXPIRED"}[i%2], AfterStatus: "DELETED", Deleted: true}
		if !row.Eligible {
			row.Deleted = false
			row.BeforeStatus = []string{"READY", "CONSUMED", "REVOKED", "RESERVED"}[i-symmetricCount]
			row.AfterStatus = row.BeforeStatus
			if i == symmetricCount {
				row.ExpiresAt = "2026-10-23T10:00:00Z"
			}
		}
		e.Rows = append(e.Rows, row)
	}
	return e
}

func symmetricRPC(t *testing.T, e *symmetricEvidence) *httptest.Server {
	t.Helper()
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.Header.Get("X-Internal-Token") != "server-secret" {
			t.Error("internal authorization missing")
			w.WriteHeader(403)
			return
		}
		var body map[string]interface{}
		if json.NewDecoder(r.Body).Decode(&body) != nil || len(body) != 0 {
			t.Error("fixed endpoint received parameters")
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": e})
	}))
	t.Cleanup(rpc.Close)
	return rpc
}

func TestSymmetricEvidenceRejectsFabricatedCountsAndInvalidSamples(t *testing.T) {
	if err := validateSymmetricEvidence(symmetricFixture()); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*symmetricEvidence){
		"no timer":           func(e *symmetricEvidence) { e.ElapsedMs = 0 },
		"no isolation":       func(e *symmetricEvidence) { e.Isolated = false },
		"no cleanup":         func(e *symmetricEvidence) { e.CleanupComplete = false },
		"no material":        func(e *symmetricEvidence) { e.MaterialVerified = false },
		"no snapshots":       func(e *symmetricEvidence) { e.Rows = nil },
		"duplicate id":       func(e *symmetricEvidence) { e.Rows[1].KeyID = e.Rows[0].KeyID },
		"duplicate material": func(e *symmetricEvidence) { e.Rows[1].KeyHash = e.Rows[0].KeyHash },
		"not symmetric":      func(e *symmetricEvidence) { e.Rows[0].Algorithm = "SM2" },
		"not expired":        func(e *symmetricEvidence) { e.Rows[0].ExpiresAt = "2026-10-23T10:00:00Z" },
		"false count":        func(e *symmetricEvidence) { e.Reclaimed-- },
		"false deletion":     func(e *symmetricEvidence) { e.Rows[0].Deleted = false },
		"wrong control":      func(e *symmetricEvidence) { e.Rows[symmetricCount].BeforeStatus = "EXPIRED" },
	} {
		t.Run(name, func(t *testing.T) {
			e := symmetricFixture()
			mutate(e)
			if validateSymmetricEvidence(e) == nil {
				t.Fatal("invalid evidence accepted")
			}
		})
	}
}

func TestSymmetricRateBoundaryAndControlsAreIndependentGates(t *testing.T) {
	for _, mode := range []string{"boundary", "slow", "control-deleted", "sample-remains"} {
		t.Run(mode, func(t *testing.T) {
			e := symmetricFixture()
			switch mode {
			case "slow":
				e.ElapsedMs = 1200.01
			case "control-deleted":
				e.Rows[symmetricCount].Deleted = true
				e.Rows[symmetricCount].AfterStatus = "DELETED"
				e.ControlsPassed--
				e.Passed = false
			case "sample-remains":
				e.Rows[0].Deleted = false
				e.Rows[0].AfterStatus = e.Rows[0].BeforeStatus
				e.Reclaimed--
				e.Remaining++
				e.Passed = false
			}
			rpc := symmetricRPC(t, e)
			s := &server{client: rpc.Client(), cfg: acceptanceConfig{SymmetricReclamationURL: rpc.URL, GenerateInternalToken: "server-secret"}}
			result := s.executeRun(context.Background(), "missing-wrk", defaultScenarios(s.cfg)["symmetric-reclaim-tps"])
			if result.Error != "" || (result.Status == "passed") != (mode == "boundary") || result.Symmetric == nil {
				t.Fatalf("incorrect verdict: %+v", result)
			}
			if result.Summary.SuccessfulRequestsPerSec != float64(e.Reclaimed)*1000/e.ElapsedMs {
				t.Fatal("rate did not use actual deletions")
			}
		})
	}
}

func TestSymmetricDemoRunsWithoutWrkAndArchivesScopedSnapshots(t *testing.T) {
	app, guard, _ := demoTestApp(t)
	rpc := symmetricRPC(t, symmetricFixture())
	guard.server.cfg.SymmetricReclamationURL = rpc.URL
	guard.server.dataDir = t.TempDir()
	guard.server.defaultWrkPath = "no-such-wrk"
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"symmetric-reclaim-tps"}`))
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
		t.Fatal("native execution timed out")
	}
	if job.result.Status != "passed" || job.result.Symmetric == nil || len(job.result.Symmetric.Rows) != 0 {
		t.Fatalf("bad native result: %+v", job.result)
	}
	status, body = demoResponse(t, app, demoRequest("GET", "/api/acceptance/lifecycle/"+run.ID+"?outcome=CONTROL_PASSED", ""))
	if status != 200 || !strings.Contains(body, `"total":4`) || !strings.Contains(body, `"algorithm":"SM4"`) || !strings.Contains(body, `"poolId":"test-pool"`) {
		t.Fatalf("missing archive: %d %s", status, body)
	}
	foreign := demoRequest("GET", "/api/acceptance/lifecycle/"+run.ID, "")
	foreign.Header.Set("Cookie", "KMS-Demo-Session=foreign")
	status, _ = demoResponse(t, app, foreign)
	if status != 404 {
		t.Fatal("cross-session archive leaked")
	}
}
