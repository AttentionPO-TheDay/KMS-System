package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSecurityControlRecordsActualReadAndIdentity(t *testing.T) {
	for _, tc := range []struct {
		name, stage, node, wantState string
		httpCode, businessCode       int
		mapped                       bool
	}{
		{"before", "攻击前验证合法节点读取", "A", "success", 200, 200, true},
		{"after", "攻击后复查合法节点读取", "A", "success", 200, 200, true},
		{"wrong-node", "攻击后复查合法节点读取", "B", "failed", 200, 200, true},
		{"unmapped", "攻击前验证合法节点读取", "A", "failed", 200, 200, false},
		{"business-error", "攻击前验证合法节点读取", "A", "failed", 200, 403, true},
		{"http-error", "攻击后复查合法节点读取", "A", "failed", 503, 503, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != "GET" || r.URL.Path != "/demo-api/pqkds/node-self/" {
					t.Errorf("unexpected control request %s %s", r.Method, r.URL.Path)
				}
				w.WriteHeader(tc.httpCode)
				json.NewEncoder(w).Encode(map[string]interface{}{
					"code": tc.businessCode, "secretKey": "must-not-leak",
					"data": map[string]interface{}{"mapped": tc.mapped, "node": map[string]string{"nodeId": tc.node}},
				})
			}))
			defer mock.Close()
			p := securityProbe{client: mock.Client(), base: mock.URL, node: "A", result: SecurityRunResult{Stage: tc.stage}}
			_, err := p.control(context.Background())
			if (err == nil) != (tc.wantState == "success") || len(p.result.ProbeSteps) != 1 {
				t.Fatalf("err=%v steps=%v", err, p.result.ProbeSteps)
			}
			step := p.result.ProbeSteps[0]
			if step.Kind != "CONTROL" || step.State != tc.wantState || step.RecordedAt == "" {
				t.Fatalf("incorrect control observation %+v", step)
			}
			if !strings.Contains(step.Detail, "expectedNodeId=A") || !strings.Contains(step.Detail, "actualNodeId="+tc.node) || strings.Contains(step.Detail, "must-not-leak") {
				t.Fatalf("missing identity evidence or leaked response: %s", step.Detail)
			}
			if strings.Contains(tc.stage, "攻击前") != strings.Contains(step.Name, "攻击前") {
				t.Fatalf("wrong control phase %s", step.Name)
			}
		})
	}
}
