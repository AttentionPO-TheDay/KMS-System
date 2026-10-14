package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

func TestCurrentSecurityCatalogAndLegacyRejection(t *testing.T) {
	seen := map[string]bool{}
	for _, group := range acceptanceCriteria() {
		for _, id := range group.CaseIDs {
			if !systemSecurityCases[id] || seen[id] {
				t.Fatalf("invalid/duplicate case %s", id)
			}
			seen[id] = true
		}
	}
	if len(seen) != 11 {
		t.Fatalf("want 11 current cases, got %d", len(seen))
	}
	result := (&server{}).executeSecurityRunContext(context.Background(), "platform-bruteforce")
	if result.Passed || result.Verdict != "not_applicable" {
		t.Fatal("legacy case must not execute or pass")
	}
}

func TestCurrentSecurityRefusesUnavailableAndWrongEvidence(t *testing.T) {
	for _, attack := range []struct {
		status   int
		code     string
		business int
		pass     bool
	}{{400, "INVALID_PARAMETER", 400, true}, {404, "INVALID_PARAMETER", 404, false}, {503, "INVALID_PARAMETER", 503, false}, {403, "NOT_AUTHORIZED", 403, false}, {200, "INVALID_PARAMETER", 200, false}, {200, "INVALID_PARAMETER", 409, true}} {
		mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			switch r.URL.Path {
			case "/demo-api/lifecycle/demo/context":
				json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"enabled": true, "csrfToken": "fixture"}})
			case "/demo-api/lifecycle/demo/context/entry":
				json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"principalType": "NODE", "csrfToken": "fixture", "revision": 1}})
			case "/demo-api/pqkds/node-self/":
				json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"mapped": true, "node": map[string]interface{}{"nodeId": "demo-0"}}})
			case "/demo-api/pqkds/node-self/keygen/issuances/":
				w.WriteHeader(attack.status)
				json.NewEncoder(w).Encode(map[string]interface{}{"code": attack.business, "data": map[string]string{"error_code": attack.code}})
			default:
				json.NewEncoder(w).Encode(map[string]int{"code": 200})
			}
		}))
		t.Setenv("ACCEPTANCE_SECURITY_GATEWAY_URL", mock.URL)
		result := (&server{}).executeSystemSecurity(context.Background(), "generation-identity-injection")
		mock.Close()
		if result.Passed != attack.pass {
			t.Fatalf("status %d code %s passed=%v", attack.status, attack.code, result.Passed)
		}
		for _, trace := range result.Requests {
			if trace.ResponseBody != "" {
				t.Fatal("must not record private response body")
			}
		}
	}
}

func TestCurrentSecurityLiveGateway(t *testing.T) {
	if os.Getenv("KMS_SECURITY_LIVE") != "1" {
		t.Skip("explicit local live gateway test only")
	}
	for _, group := range acceptanceCriteria() {
		for _, id := range group.CaseIDs {
			t.Run(id, func(t *testing.T) {
				result := (&server{}).executeSystemSecurity(context.Background(), id)
				if !result.Passed {
					t.Fatalf("%s: %s %s", result.Status, result.Summary, result.Error)
				}
				t.Log(result.Summary)
			})
			time.Sleep(400 * time.Millisecond)
		}
	}
}
