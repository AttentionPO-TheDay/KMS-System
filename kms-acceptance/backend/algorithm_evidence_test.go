package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func testAlgorithmEvidence(caseID string) AlgorithmEvidence {
	e := AlgorithmEvidence{Version: 1, CaseID: caseID, Category: "fixture", Source: "native fixture", Scope: "fixture", Passed: true}
	for _, id := range algorithmCheckIDs(caseID) {
		e.Checks = append(e.Checks, AlgorithmCheck{ID: id, Name: id, Expected: "expected", Actual: "actual", Passed: true, Status: "passed", RecordedAt: "2026-10-19T00:00:00Z"})
	}
	return e
}

func TestPQRequiresCompleteAlgorithmsInSameRun(t *testing.T) {
	for _, mode := range []string{"pass", "missing", "duplicate", "failed", "error", "contradictory", "unavailable"} {
		t.Run(mode, func(t *testing.T) {
			id := "pq-parameter-downgrade"
			e := testAlgorithmEvidence(id)
			switch mode {
			case "missing":
				e.Checks = e.Checks[:1]
			case "duplicate":
				e.Checks[1].ID = e.Checks[0].ID
			case "failed", "contradictory":
				e.Checks[2].Passed, e.Checks[2].Status = false, "failed"
				e.Passed = mode == "contradictory"
			case "error":
				e.Checks[2].Passed, e.Checks[2].Status, e.Passed = false, "error", false
			}
			gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				switch r.URL.Path {
				case "/demo-api/lifecycle/demo/context":
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"enabled": true, "csrfToken": "fixture"}})
				case "/demo-api/lifecycle/demo/context/entry":
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"principalType": "NODE", "csrfToken": "fixture", "revision": 1}})
				case "/demo-api/pqkds/node-self/":
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"mapped": true, "node": map[string]string{"nodeId": "A"}}})
				case "/demo-api/pqkds/node-self/keygen/issuances/":
					w.WriteHeader(400)
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 400, "msg": "生成参数集无效", "data": map[string]string{"error_code": "KYBER_KEYGEN_VARIANT_INVALID"}})
				case "/demo-api/pqkds/node-self/acceptance/pq/":
					if mode == "unavailable" {
						w.WriteHeader(503)
						json.NewEncoder(w).Encode(map[string]int{"code": 503})
						return
					}
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": e})
				default:
					json.NewEncoder(w).Encode(map[string]int{"code": 200})
				}
			}))
			defer gateway.Close()
			t.Setenv("ACCEPTANCE_SECURITY_GATEWAY_URL", gateway.URL)
			t.Setenv("ACCEPTANCE_SECURITY_NODE_ID", "A")
			result := (&server{}).executeSystemSecurity(context.Background(), id)
			if !result.ProtocolPassed || result.Passed != (mode == "pass") || result.EvidenceVersion != 3 {
				t.Fatalf("incorrect combined result: %+v", result)
			}
			if mode == "failed" && (result.Status != "completed" || result.Verdict != "vulnerable") {
				t.Fatal("real failed assertion must stay visibly failed")
			}
			if mode == "error" && result.Status != "error" {
				t.Fatal("native errors must not count as successful rejection")
			}
		})
	}
}
