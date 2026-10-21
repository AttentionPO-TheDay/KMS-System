package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

func auditTestRecord(id int64, status string, version int) internalVerifyRecord {
	return internalVerifyRecord{KeyID: id, Exists: true, Status: status, Version: &version, UserName: "acceptance_user", KeyDomain: "acceptance", ChainStatus: "1", MaterialDigest: fmt.Sprint("material-", version)}
}

func TestAuditUpdateDoesNotCountPreexistingChainSuccess(t *testing.T) {
	before := auditTestRecord(1, "0", 1)
	same := auditTestRecord(1, "0", 1)
	changed := auditTestRecord(1, "0", 2)
	if auditOutcome("update-tps", before, &same) != "PENDING" {
		t.Fatal("old chain success counted as update")
	}
	if auditOutcome("update-tps", before, &changed) != "COMPLETED" {
		t.Fatal("version change not counted")
	}
	unchangedMaterial := changed
	unchangedMaterial.MaterialDigest = before.MaterialDigest
	if auditOutcome("update-tps", before, &unchangedMaterial) != "PENDING" {
		t.Fatal("a version increment without new material must not count as an update")
	}
	revoked := auditTestRecord(1, "3", 1)
	if auditOutcome("revoke-rate", revoked, &revoked) != "EXCLUDED" {
		t.Fatal("already revoked counted")
	}
	if auditOutcome("revoke-rate", before, nil) != "UNVERIFIED" {
		t.Fatal("missing observation counted")
	}
	rate := 0.0
	result := applyLifecycleAuditResult(Scenario{ID: "update-tps", MetricKind: "update_final_rate", MetricTarget: 98, MetricOperator: ">="},
		&lifecycleArchive{Batch: lifecycleBatch{Eligible: 1, CompletionRate: &rate}}, RunResult{Status: "passed", PassedTPS: true})
	if result.Status != "failed_threshold" || result.MetricCheck.Passed {
		t.Fatal("unchanged version incorrectly passes final-state check")
	}
}

func TestAuditCountsEligibleKeysAndUnknownIsNotZero(t *testing.T) {
	archive := &lifecycleArchive{Batch: lifecycleBatch{ScenarioID: "revoke-rate", Eligible: 2, Excluded: 1}}
	rows := []lifecycleRow{{KeyID: 1, Before: auditTestRecord(1, "0", 1)}, {KeyID: 2, Before: auditTestRecord(2, "0", 1)}, {KeyID: 3, Before: auditTestRecord(3, "3", 1)}}
	summarizeAudit(archive, rows, map[int64]internalVerifyRecord{1: auditTestRecord(1, "3", 1), 2: auditTestRecord(2, "0", 1), 3: auditTestRecord(3, "3", 1)})
	if archive.Batch.Completed != 1 || archive.Batch.Pending != 1 || archive.Batch.CompletionRate == nil || *archive.Batch.CompletionRate != 50 {
		t.Fatalf("bad counts: %+v", archive.Batch)
	}
	rows[1].After = nil
	summarizeAudit(archive, rows, map[int64]internalVerifyRecord{1: auditTestRecord(1, "3", 1)})
	if archive.Batch.CompletionRate != nil || archive.Batch.Unknown != 1 {
		t.Fatal("unknown reported as measured zero")
	}
}

func TestAuditSnapshotCaptureRejectsWrongOwnerMissingDuplicateAndLegacy(t *testing.T) {
	for _, mode := range []string{"valid", "foreign", "missing", "duplicate", "legacy", "wrong-id"} {
		t.Run(mode, func(t *testing.T) {
			rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Header.Get("X-Internal-Token") != "test-private" {
					t.Error("internal authorization missing")
				}
				record := auditTestRecord(1, "0", 1)
				rows := []internalVerifyRecord{record}
				switch mode {
				case "foreign":
					rows[0].KeyDomain = "business"
				case "missing":
					rows = nil
				case "duplicate":
					rows = append(rows, record)
				case "legacy":
					rows[0].Version = nil
				case "wrong-id":
					rows[0].KeyID = 9
				}
				json.NewEncoder(w).Encode(internalVerifyResponse{Data: rows})
			}))
			defer rpc.Close()
			s := &server{client: rpc.Client(), cfg: acceptanceConfig{LifecycleVerifyURL: rpc.URL, GenerateInternalToken: "test-private", AcceptanceUser: "acceptance_user"}}
			_, err := s.captureLifecycle(context.Background(), []int64{1})
			if (err == nil) != (mode == "valid") {
				t.Fatalf("mode %s err=%v", mode, err)
			}
		})
	}
}

func TestAuditArchivePaginationSessionIsolationAndRestart(t *testing.T) {
	s := &server{dataDir: t.TempDir()}
	rows := make([]lifecycleRow, 321)
	for i := range rows {
		rows[i] = lifecycleRow{KeyID: int64(i + 1), Before: auditTestRecord(int64(i+1), "0", 1), Outcome: "PENDING"}
	}
	archive := lifecycleArchive{Owner: lifecycleOwner("test-owner"), Revision: 1, Phase: "before", Batch: lifecycleBatch{ID: "run-test-1", ScenarioID: "update-tps", PoolSize: 321, Eligible: 321}}
	if err := s.saveLifecycleAudit(archive, rows); err != nil {
		t.Fatal(err)
	}
	// New guard, no in-memory jobs: reads use the persisted, ownership-scoped archive.
	g := &demoGuard{server: s}
	for _, test := range []struct {
		session, path        string
		revision             int64
		status, total, count int
	}{
		{"test-owner", "/api/acceptance/lifecycle/run-test-1?page=16&pageSize=20", 1, 200, 321, 20},
		{"test-owner", "/api/acceptance/lifecycle/run-test-1?page=17&pageSize=20", 1, 200, 321, 1},
		{"test-owner", "/api/acceptance/lifecycle/run-test-1?outcome=COMPLETED", 1, 200, 0, 0},
		{"another-session", "/api/acceptance/lifecycle/run-test-1", 1, 404, 0, 0},
		{"test-owner", "/api/acceptance/lifecycle/run-test-1", 2, 404, 0, 0},
		{"test-owner", "/api/acceptance/lifecycle/run-test-1?pageSize=200", 1, 400, 0, 0},
	} {
		app := fiber.New()
		app.Get("/*", func(c *fiber.Ctx) error { return g.readLifecycleAudit(c, test.session, test.revision) })
		resp, err := app.Test(httptest.NewRequest("GET", test.path, nil))
		if err != nil {
			t.Fatal(err)
		}
		data, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		if resp.StatusCode != test.status {
			t.Fatalf("%s status %d: %s", test.path, resp.StatusCode, data)
		}
		if resp.StatusCode == 200 {
			var result struct {
				Total int            `json:"total"`
				Items []lifecycleRow `json:"items"`
			}
			json.Unmarshal(data, &result)
			if result.Total != test.total || len(result.Items) != test.count {
				t.Fatalf("pagination %+v", result)
			}
			if strings.Contains(string(data), "owner") || strings.Contains(string(data), "test-owner") {
				t.Fatal("owner/session leaked")
			}
		}
	}
	for _, method := range []string{"POST", "PUT", "DELETE"} {
		if canonicalDemoRoute(method, "/api/acceptance/lifecycle/run-test-1") {
			t.Fatal("audit writes exposed")
		}
	}
	if canonicalDemoRoute("GET", "/api/acceptance/lifecycle/../runs") {
		t.Fatal("path traversal accepted")
	}
}

func TestAuditGuardListPagingAndAuthority(t *testing.T) {
	app, guard, authority := demoTestApp(t)
	guard.server.dataDir = t.TempDir()
	for i := 0; i < 25; i++ {
		archive := lifecycleArchive{Owner: lifecycleOwner("owner"), Revision: 1, Phase: "before", Batch: lifecycleBatch{ID: fmt.Sprintf("run-list-%02d", i), ScenarioID: "update-tps", StartedAt: fmt.Sprintf("2026-10-14T00:00:%02dZ", i)}}
		if i >= 22 {
			archive.Owner = lifecycleOwner("other")
		}
		if err := guard.server.saveLifecycleAudit(archive, []lifecycleRow{}); err != nil {
			t.Fatal(err)
		}
	}
	status, body := demoResponse(t, app, demoRequest("GET", "/api/acceptance/lifecycle?scenario=update-tps&page=2&pageSize=20", ""))
	var result struct {
		Total int              `json:"total"`
		Items []lifecycleBatch `json:"items"`
	}
	if status != 200 || json.Unmarshal([]byte(body), &result) != nil || result.Total != 22 || len(result.Items) != 2 || result.Items[0].ID != "run-list-01" {
		t.Fatalf("guard list paging failed: %d %s", status, body)
	}
	status, _ = demoResponse(t, app, demoRequest("GET", "/api/acceptance/lifecycle/run-list-24", ""))
	if status != 404 {
		t.Fatal("another session's archive was visible")
	}
	authority.mu.Lock()
	authority.role = "NODE"
	authority.mu.Unlock()
	status, _ = demoResponse(t, app, demoRequest("GET", "/api/acceptance/lifecycle", ""))
	if status != 403 {
		t.Fatalf("node read admin archive: %d", status)
	}
}

func TestAuditPersistsBeforeAndAfterWithoutSecretsOrFakeConfirmation(t *testing.T) {
	version := 1
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(internalVerifyResponse{Data: []internalVerifyRecord{auditTestRecord(1, "0", version)}})
	}))
	defer rpc.Close()
	s := &server{dataDir: t.TempDir(), client: rpc.Client(), cfg: acceptanceConfig{AcceptanceUser: "acceptance_user", LifecycleVerifyURL: rpc.URL}}
	archive, rows, err := s.beginLifecycleAudit(context.Background(), Scenario{ID: "update-tps", PreparedKeyIDs: []int64{1}}, RunResult{ID: "run-test-2"}, "secret-cookie", 1)
	if err != nil {
		t.Fatal(err)
	}
	version = 2
	if err = s.finishLifecycleAudit(context.Background(), archive, rows, RunResult{Status: "passed", Summary: RunSummary{SuccessfulRequestsPerSec: 6000, RawOutput: "DO_NOT_STORE_RAW_OR_TOKEN"}}); err != nil {
		t.Fatal(err)
	}
	if archive.Batch.Completed != 1 || rows[0].Before.Version == nil || *rows[0].Before.Version != 1 || *rows[0].After.Version != 2 {
		t.Fatal("snapshot mutated")
	}
	for _, name := range []string{"run-test-2.summary.json", "run-test-2-final.json"} {
		data, _ := os.ReadFile(filepath.Join(s.auditDirectory(), name))
		if strings.Contains(string(data), "secret-cookie") || strings.Contains(string(data), "DO_NOT_STORE") {
			t.Fatal("sensitive data stored")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err = s.finishLifecycleAudit(ctx, archive, rows, RunResult{Status: "cancelled"}); err != nil {
		t.Fatal(err)
	}
	if archive.Batch.CompletionRate != nil || archive.Batch.Error == "" {
		t.Fatal("cancelled verification incorrectly confirmed")
	}
}

func TestAuditKeyCaptureChunksDoNotCapAt200(t *testing.T) {
	calls := 0
	rpc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		items := []internalVerifyRecord{}
		for _, value := range r.URL.Query()["keyIds"] {
			var id int64
			fmt.Sscan(value, &id)
			items = append(items, auditTestRecord(id, "0", 1))
		}
		json.NewEncoder(w).Encode(internalVerifyResponse{Data: items})
	}))
	defer rpc.Close()
	ids := make([]int64, 321)
	for i := range ids {
		ids[i] = int64(i + 1)
	}
	s := &server{client: rpc.Client(), cfg: acceptanceConfig{AcceptanceUser: "acceptance_user", LifecycleVerifyURL: rpc.URL}}
	records, err := s.captureLifecycle(context.Background(), ids)
	if err != nil || len(records) != 321 || calls != 2 {
		t.Fatalf("records=%d calls=%d err=%v", len(records), calls, err)
	}
}
