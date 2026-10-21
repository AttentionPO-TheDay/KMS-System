package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func fixedUpdateIDs() []int64 {
	ids := make([]int64, fixedUpdateCount)
	for i := range ids {
		ids[i] = int64(i + 1)
	}
	return ids
}

func TestFixedUpdatePreparationRequests6000ExistingValidKeys(t *testing.T) {
	started := time.Date(2026, 10, 21, 17, 0, 0, 0, time.FixedZone("CST", 8*3600))
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("limit") != "6000" || r.URL.Query().Get("activeOnly") != "true" || r.URL.Query().Get("createdAfter") != "" || r.URL.Query().Get("encrytName") != "SM2" {
			t.Errorf("wrong bounded generation query: %s", r.URL.RawQuery)
		}
		rows := make([]internalKeyRecord, fixedUpdateCount)
		for i := range rows {
			rows[i] = internalKeyRecord{KeyID: int64(i + 1), UserName: "acceptance_user", Status: "0", KeyDomain: "acceptance"}
		}
		json.NewEncoder(w).Encode(internalGenerateResponse{Data: rows})
	}))
	defer rpc.Close()
	s := &server{client: rpc.Client(), cfg: acceptanceConfig{GenerateKeyPoolURL: rpc.URL, AcceptanceUser: "acceptance_user", LifecycleRequiredKeys: 25000}}
	scenario := defaultScenarios(s.cfg)["update-tps"]
	scenario.GeneratedAfter, scenario.SourceRunID = started, "source-generation"
	prepared, _, err := s.prepareScenarioContext(context.Background(), scenario)
	if err != nil || len(prepared.PreparedKeyIDs) != 6000 || prepared.SourceRunID != "" {
		t.Fatalf("bad preparation: %v", err)
	}
}

func TestFixedUpdateSendsEachKeyOncePerRunAndNeverCountsDuplicatesAsAcceptance(t *testing.T) {
	var mu sync.Mutex
	counts, idempotency := map[int64]int{}, map[string]bool{}
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			KeyID int64 `json:"keyId"`
		}
		json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		counts[body.KeyID]++
		key := r.Header.Get("Idempotency-Key")
		if key == "" || idempotency[key] {
			t.Error("idempotency reused across keys or runs")
		}
		idempotency[key] = true
		mu.Unlock()
		if body.KeyID == 1 {
			w.WriteHeader(202)
			fmt.Fprint(w, `{"code":202,"status":"duplicate"}`)
			return
		}
		if body.KeyID == 2 {
			fmt.Fprint(w, `{"code":500,"status":"error"}`)
			return
		}
		fmt.Fprint(w, `{"code":200,"status":"accepted"}`)
	}))
	defer rpc.Close()
	s := &server{client: rpc.Client()}
	scenario := Scenario{ID: "update-tps", BaseURL: rpc.URL, Path: "/UPDATE_KEY", Connections: 50, PreparedKeyIDs: fixedUpdateIDs(), BodyTemplate: `{"keyId":{{KEY_ID}}}`}
	for i := 0; i < 2; i++ {
		run := s.executeRun(context.Background(), "missing-wrk", scenario)
		if run.Error != "" || run.FixedUpdate.Submitted != 6000 || run.FixedUpdate.Accepted != 5998 || run.FixedUpdate.Duplicates != 1 || run.FixedUpdate.Rejected != 1 {
			t.Fatalf("wrong finite workload: %+v", run.FixedUpdate)
		}
	}
	if len(counts) != 6000 || len(idempotency) != 12000 {
		t.Fatal("workload identity mismatch")
	}
	for _, count := range counts {
		if count != 2 {
			t.Fatal("key repeated or skipped within a run")
		}
	}
}

func TestFixedUpdateUsesVersionCompletionTimeInsteadOfAcceptedTPS(t *testing.T) {
	rate := 100.0
	archive := &lifecycleArchive{Batch: lifecycleBatch{Eligible: 6000, Completed: 6000, CompletionRate: &rate}}
	result := RunResult{Status: "failed_threshold", FixedUpdate: &fixedUpdateEvidence{Version: 1, Submitted: 6000, AcceptedTPS: 20000, StartedAt: time.Now().Add(-10 * time.Second).Format(time.RFC3339Nano)}}
	scenario := Scenario{ID: "update-tps", TargetTPS: 5000, TargetOperator: ">=", MetricKind: "update_final_rate", MetricTarget: 98, MetricOperator: ">="}
	result = applyLifecycleAuditResult(scenario, archive, result)
	if !result.FixedUpdate.Verified || !result.MetricCheck.Passed || result.Summary.SuccessfulRequestsPerSec > 601 || result.PassedTPS || result.Status != "failed_threshold" {
		t.Fatal("accepted HTTP throughput incorrectly certified an update")
	}
}

func TestFixedUpdateDemoNoWrkAndArchivesAll6000VersionChanges(t *testing.T) {
	app, guard, _ := demoTestApp(t)
	var submitted atomic.Int64
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/pool":
			if r.URL.Query().Get("limit") != "6000" {
				t.Error("update fetched more than 6000 keys")
			}
			rows := make([]internalKeyRecord, 6000)
			for i := range rows {
				rows[i] = internalKeyRecord{KeyID: int64(i + 1), UserName: "acceptance_user", Status: "0", KeyDomain: "acceptance"}
			}
			json.NewEncoder(w).Encode(internalGenerateResponse{Data: rows})
		case "/status":
			version := 1
			if submitted.Load() == 6000 {
				version = 2
			}
			rows := []internalVerifyRecord{}
			for _, value := range r.URL.Query()["keyIds"] {
				id, _ := strconv.ParseInt(value, 10, 64)
				rows = append(rows, internalVerifyRecord{KeyID: id, Exists: true, Status: "0", Version: &version, UserName: "acceptance_user", KeyDomain: "acceptance", MaterialDigest: fmt.Sprint("material-", version)})
			}
			json.NewEncoder(w).Encode(internalVerifyResponse{Data: rows})
		case "/lifecycle/request/UPDATE_KEY":
			submitted.Add(1)
			fmt.Fprint(w, `{"code":200,"status":"accepted"}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	defer rpc.Close()
	guard.server.cfg.AcceptanceUser = "acceptance_user"
	guard.server.cfg.GenerateKeyPoolURL = rpc.URL + "/pool"
	guard.server.cfg.LifecycleVerifyURL = rpc.URL + "/status"
	guard.server.dataDir = t.TempDir()
	guard.server.defaultWrkPath = "missing-wrk"
	scenario := defaultScenarios(acceptanceConfig{AcceptanceUser: "acceptance_user", UpdateVerifyTarget: 98})["update-tps"]
	scenario.BaseURL = rpc.URL
	guard.server.scenarios["update-tps"] = scenario
	status, body := demoResponse(t, app, demoRequest("POST", "/api/runs", `{"scenarioId":"update-tps"}`))
	if status != 202 {
		t.Fatalf("%d %s", status, body)
	}
	var run RunResult
	json.Unmarshal([]byte(body), &run)
	guard.mu.RLock()
	job := guard.jobs[run.ID]
	guard.mu.RUnlock()
	select {
	case <-job.done:
	case <-time.After(12 * time.Second):
		t.Fatal("fixed update did not complete")
	}
	if job.result.Error != "" || job.result.FixedUpdate == nil || !job.result.FixedUpdate.Verified || job.result.FixedUpdate.Completed != 6000 || submitted.Load() != 6000 {
		t.Fatalf("fixed update failed: %+v", job.result)
	}
	if job.audit.Batch.PoolSize != 6000 || len(job.auditRows) != 6000 || job.audit.Batch.Completed != 6000 {
		t.Fatal("incomplete version archive")
	}
}
