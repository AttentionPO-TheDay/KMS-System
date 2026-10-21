package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
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
	if len(seen) != 14 {
		t.Fatalf("want 14 current cases, got %d", len(seen))
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
		reason   string
	}{
		{400, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 400, true, "签发只接受白名单字段，可信上下文由后端确定"},
		{404, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 404, false, "签发只接受白名单字段，可信上下文由后端确定"},
		{503, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 503, false, "签发只接受白名单字段，可信上下文由后端确定"},
		{403, "NOT_AUTHORIZED", 403, false, "签发只接受白名单字段，可信上下文由后端确定"},
		{200, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 200, false, "签发只接受白名单字段，可信上下文由后端确定"},
		{200, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 409, true, "签发只接受白名单字段，可信上下文由后端确定"},
		{200, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 409, false, "生成参数集无效"},
		{200, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 409, false, ""},
		{200, "KEYGEN_IDENTITY_FIELD_FORBIDDEN", 409, false, "secretKey=must-not-be-recorded"},
	} {
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
				json.NewEncoder(w).Encode(map[string]interface{}{"code": attack.business, "msg": attack.reason, "data": map[string]string{"error_code": attack.code}})
			default:
				json.NewEncoder(w).Encode(map[string]int{"code": 200})
			}
		}))
		t.Setenv("ACCEPTANCE_SECURITY_GATEWAY_URL", mock.URL)
		t.Setenv("ACCEPTANCE_SECURITY_NODE_ID", "demo-0")
		result := (&server{}).executeSystemSecurity(context.Background(), "generation-identity-injection")
		mock.Close()
		if result.Passed != attack.pass {
			t.Fatalf("status %d code %s passed=%v", attack.status, attack.code, result.Passed)
		}
		if result.Passed && (!result.ReasonMatched || result.EvidenceVersion != 2 || result.ExpectedReason != result.ActualReason) {
			t.Fatal("a pass requires matching reason evidence")
		}
		if attack.reason == "secretKey=must-not-be-recorded" && result.ActualReason != "" {
			t.Fatal("unreviewed rejection messages must not be persisted")
		}
		for _, trace := range result.Requests {
			if strings.Contains(trace.Message, "must-not-be-recorded") {
				t.Fatal("unreviewed response message leaked into trace")
			}
			if trace.ResponseBody != "" {
				t.Fatal("must not record private response body")
			}
		}
	}
}

func TestCurrentSecurityUsesExistingNode(t *testing.T) {
	for _, tc := range []struct {
		name, configured, want string
		available              bool
	}{
		{"default-A", "", "A", true},
		{"configured-B", "B", "B", true},
		{"configured-C", "C", "C", true},
		{"unavailable-node", "missing", "missing", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			attacks, entries := 0, 0
			mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				switch r.URL.Path {
				case "/demo-api/lifecycle/demo/context":
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"enabled": true, "csrfToken": "fixture"}})
				case "/demo-api/lifecycle/demo/context/entry":
					entries++
					var body struct {
						NodeID string `json:"nodeId"`
					}
					if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.NodeID != tc.want {
						t.Errorf("entry node=%q, want %q; error=%v", body.NodeID, tc.want, err)
					}
					if !tc.available {
						w.WriteHeader(http.StatusNotFound)
						json.NewEncoder(w).Encode(map[string]int{"code": 404})
						return
					}
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"principalType": "NODE", "csrfToken": "fixture", "revision": 1}})
				case "/demo-api/pqkds/node-self/":
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"mapped": true, "node": map[string]string{"nodeId": tc.want}}})
				case "/demo-api/pqkds/node-self/keygen/issuances/":
					attacks++
					w.WriteHeader(http.StatusBadRequest)
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 400, "msg": "签发只接受白名单字段，可信上下文由后端确定", "data": map[string]string{"error_code": "KEYGEN_IDENTITY_FIELD_FORBIDDEN"}})
				case "/demo-api/lifecycle/demo/context/logout":
					json.NewEncoder(w).Encode(map[string]int{"code": 200})
				default:
					t.Errorf("unexpected endpoint (must not create nodes): %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer mock.Close()
			t.Setenv("ACCEPTANCE_SECURITY_GATEWAY_URL", mock.URL)
			t.Setenv("ACCEPTANCE_SECURITY_NODE_ID", tc.configured)
			var progress []SecurityRunResult
			ctx := context.WithValue(context.Background(), securityProgressKey{}, func(snapshot SecurityRunResult) {
				progress = append(progress, snapshot)
			})
			result := (&server{}).executeSystemSecurity(ctx, "generation-identity-injection")
			if entries != 1 || result.Passed != tc.available {
				t.Fatalf("entries=%d passed=%v error=%s", entries, result.Passed, result.Error)
			}
			if tc.available && (result.ExpectedCode != "KEYGEN_IDENTITY_FIELD_FORBIDDEN" || result.ActualCode != result.ExpectedCode || !result.LegalControlPassed) {
				t.Fatal("a pass must expose rejection evidence and a successful legal control")
			}
			if tc.available {
				if len(result.Requests) != 5 || len(progress) < 5 || len(progress[0].Requests) != 0 {
					t.Fatal("must publish intermediate steps without mutating earlier snapshots")
				}
				for _, trace := range result.Requests {
					if trace.Name == "" || trace.RecordedAt == "" || trace.DurationMs < 0 {
						t.Fatal("each request needs an actual step, timestamp and duration")
					}
				}
			}
			if !tc.available && (attacks != 0 || result.Status != "error") {
				t.Fatal("unavailable node must stop before the attack without creating a node")
			}
		})
	}
}

func TestCurrentSecurityLiveGateway(t *testing.T) {
	if os.Getenv("KMS_SECURITY_LIVE") != "1" {
		t.Skip("explicit local live gateway test only")
	}
	seenCodes := map[string]string{}
	for _, group := range acceptanceCriteria() {
		for _, id := range group.CaseIDs {
			t.Run(id, func(t *testing.T) {
				result := (&server{}).executeSystemSecurity(context.Background(), id)
				if !result.Passed {
					t.Fatalf("%s: %s %s", result.Status, result.Summary, result.Error)
				}
				if previous, duplicate := seenCodes[result.ActualCode]; duplicate {
					t.Fatalf("duplicate rejection code %s in %s and %s", result.ActualCode, previous, id)
				}
				seenCodes[result.ActualCode] = id
				t.Log(result.Summary)
			})
			time.Sleep(400 * time.Millisecond)
		}
	}
}
