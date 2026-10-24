package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestProbeStepsObserveActualAttackOperations(t *testing.T) {
	counts := map[int]bool{}
	for _, tc := range []struct {
		id, code, reason string
	}{
		{"generation-identity-injection", "KEYGEN_IDENTITY_FIELD_FORBIDDEN", "签发只接受白名单字段，可信上下文由后端确定"},
		{"generation-unknown-algorithm", "KEYGEN_SCHEME_INVALID", "签发仅支持规范 KYBER/FALCON 家族"},
		{"generation-malformed-json", "KEYGEN_JSON_INVALID", "请求参数或 JSON 无效"},
		{"generation-invalid-version", "KEYGEN_VERSION_INVALID", "keyVersion 应为 ≥1 的整数：1.5"},
		{"network-session-forgery", "DEMO_SESSION_INVALID", "DEMO_SESSION_INVALID"},
		{"network-missing-session", "DEMO_SESSION_REQUIRED", "缺少 Demo 会话"},
		{"network-csrf", "DEMO_CSRF_INVALID", "DEMO_CSRF_INVALID"},
		{"network-stale-revision", "DEMO_REVISION_STALE", "DEMO_REVISION_STALE"},
		{"network-role-isolation", "DEMO_FORBIDDEN", "演示节点不能访问管理接口"},
		{"network-origin", "DEMO_ORIGIN_REJECTED", "DEMO_ORIGIN_REJECTED"},
	} {
		t.Run(tc.id, func(t *testing.T) {
			attacks := 0
			mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				switch r.URL.Path {
				case "/demo-api/lifecycle/demo/context":
					http.SetCookie(w, &http.Cookie{Name: "KMS-Demo-Session", Value: "fixture-session-sensitive", Path: "/"})
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"enabled": true, "csrfToken": "fixture-csrf-sensitive"}})
					return
				case "/demo-api/lifecycle/demo/context/entry":
					json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"principalType": "NODE", "csrfToken": "fixture-csrf-sensitive", "revision": 3}})
					return
				case "/demo-api/lifecycle/demo/context/logout":
					json.NewEncoder(w).Encode(map[string]int{"code": 200})
					return
				case "/demo-api/pqkds/node-self/":
					if r.Header.Get("Cookie") == "KMS-Demo-Session=fixture-session-sensitive" {
						json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": map[string]interface{}{"mapped": true, "node": map[string]string{"nodeId": "A"}}})
						return
					}
				}
				attacks++
				raw, _ := io.ReadAll(r.Body)
				switch tc.id {
				case "generation-identity-injection":
					var data map[string]interface{}
					if json.Unmarshal(raw, &data) != nil || data["nodeId"] != "foreign-node" {
						t.Error("identity injection was not sent")
					}
				case "generation-malformed-json":
					if json.Valid(raw) {
						t.Error("malformed JSON was silently repaired")
					}
				case "network-session-forgery":
					if r.Header.Get("Cookie") != "KMS-Demo-Session="+strings.Repeat("A", 43) {
						t.Error("forged request included legitimate session")
					}
				case "network-missing-session":
					if r.Header.Get("Cookie") != "" {
						t.Error("anonymous request included cookies")
					}
				case "network-stale-revision":
					if r.Header.Get("X-Kms-Demo-Revision") != "2" {
						t.Error("old revision was not sent")
					}
				case "network-csrf":
					if r.Header.Get("X-Kms-Demo-CSRF") != "acceptance-invalid" {
						t.Error("CSRF mutation was not sent")
					}
				case "network-origin":
					if r.Header.Get("Origin") != "https://acceptance-invalid.example" {
						t.Error("origin mutation was not sent")
					}
				}
				w.WriteHeader(403)
				json.NewEncoder(w).Encode(map[string]interface{}{"code": 403, "msg": tc.reason, "data": map[string]string{"error_code": tc.code}})
			}))
			defer mock.Close()
			t.Setenv("ACCEPTANCE_SECURITY_GATEWAY_URL", mock.URL)
			t.Setenv("ACCEPTANCE_SECURITY_NODE_ID", "A")
			var snapshots []SecurityRunResult
			ctx := context.WithValue(context.Background(), securityProgressKey{}, func(s SecurityRunResult) { snapshots = append(snapshots, s) })
			r := (&server{}).executeSystemSecurity(ctx, tc.id)
			if !r.Passed || attacks != 1 || len(r.ProbeSteps) < 2 {
				t.Fatalf("passed=%v attacks=%d steps=%d error=%s", r.Passed, attacks, len(r.ProbeSteps), r.Error)
			}
			counts[len(r.ProbeSteps)] = true
			if len(snapshots[0].ProbeSteps) != 0 {
				t.Fatal("earlier snapshots changed")
			}
			for _, step := range r.ProbeSteps {
				if _, err := time.Parse(time.RFC3339Nano, step.RecordedAt); err != nil {
					t.Fatal("step needs actual timestamp")
				}
				if strings.Contains(step.Detail, "fixture-") {
					t.Fatal("credentials entered execution logs")
				}
			}
			assertions, controls := 0, 0
			for _, step := range r.ProbeSteps {
				if step.Kind == "ASSERT" {
					assertions++
					if step.State != "success" {
						t.Fatal("attack rejection observation must succeed")
					}
				}
				if step.Kind == "CONTROL" {
					controls++
					if step.State != "success" {
						t.Fatal("legal business observation must succeed")
					}
				}
			}
			if assertions == 0 || controls != 2 {
				t.Fatalf("expected rejection and before/after controls: assertions=%d controls=%d", assertions, controls)
			}
		})
	}
	if len(counts) < 3 {
		t.Fatalf("expected varying recorded operations, got %v", counts)
	}
}
