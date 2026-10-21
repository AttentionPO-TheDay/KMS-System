package main

import (
	"math"
	"strings"
	"testing"
)

func TestParseWrkOutputSeparatesSocketAndHTTPErrors(t *testing.T) {
	output := `
Latency   1.20ms   2.00ms   3.10ms
Requests/sec: 100000.00
Transfer/sec: 10.00MB
100 requests in 1.00s, 1.00MB read
Socket errors: connect 2, read 3, write 4, timeout 1
Non-2xx or 3xx responses: 10
99%   3.10ms
`
	summary := parseWrkOutput(output)
	if summary.TotalRequests != 100 {
		t.Fatalf("total requests = %d, want 100", summary.TotalRequests)
	}
	if summary.SocketErrors != 10 || summary.Non2xxResponses != 10 || summary.ErrorCount != 20 {
		t.Fatalf("error split = socket %d non2xx %d total %d, want 10/10/20", summary.SocketErrors, summary.Non2xxResponses, summary.ErrorCount)
	}
	if math.Abs(summary.SuccessRate-81.81818181818181) > 1e-9 {
		t.Fatalf("success rate = %v, want 81.81818181818181", summary.SuccessRate)
	}
}

func TestSuccessfulRateUsesCompletedHTTPRequestsOnly(t *testing.T) {
	summary := parseWrkOutput("100 requests in 2.00s, 1.00MB read\nSocket errors: connect 5, read 0, write 0, timeout 0\nNon-2xx or 3xx responses: 10\n")
	successful := summary.TotalRequests - summary.Non2xxResponses
	if successful != 90 {
		t.Fatalf("successful requests = %d, want 90", successful)
	}
}

func TestAcceptanceCriteriaExposeStrictThresholds(t *testing.T) {
	items := acceptanceCriteria()
	if len(items) != 8 {
		t.Fatalf("criteria = %d, want 8", len(items))
	}
	want := map[string]struct {
		operator string
		target   float64
	}{
		"certless-generation": {operator: ">", target: 100000},
		"preallocation":       {operator: ">", target: 50},
		"key-update":          {operator: ">=", target: 5000},
		"abnormal-revoke":     {operator: ">=", target: 5000},
		"revoke-rate":         {operator: ">=", target: 98},
	}
	for _, item := range items {
		if expected, ok := want[item.ID]; ok && (item.Operator != expected.operator || item.Target != expected.target) {
			t.Fatalf("%s threshold = %s %v, want %s %v", item.ID, item.Operator, item.Target, expected.operator, expected.target)
		}
	}
	if compareThreshold(100000, ">", 100000) || !compareThreshold(100001, ">", 100000) {
		t.Fatal("strict greater-than threshold is not enforced")
	}
	if compareThreshold(97.99, ">=", 98) || !compareThreshold(98, ">=", 98) || !compareThreshold(100, ">=", 98) {
		t.Fatal("inclusive revoke-rate threshold is not enforced")
	}
}

func TestAcceptanceSecurityCriteriaUseRequiredCaseCounts(t *testing.T) {
	for _, item := range acceptanceCriteria() {
		switch item.ID {
		case "generation-attacks":
			if len(item.CaseIDs) != 4 || item.Target != 3 {
				t.Fatalf("generation attacks = %d, want 4 with target 3", len(item.CaseIDs))
			}
		case "quantum-attacks":
			if len(item.CaseIDs) != 4 || item.Target != 3 {
				t.Fatalf("quantum attacks = %d, want 4 with target 3", len(item.CaseIDs))
			}
		case "network-attacks":
			if len(item.CaseIDs) != 6 || item.Target != 5 {
				t.Fatalf("network attacks = %d, want 6 with target 5", len(item.CaseIDs))
			}
		}
	}
}

func TestPreallocationCriterionRequiresAnExplicitNodeRun(t *testing.T) {
	for _, item := range acceptanceCriteria() {
		if item.ID != "preallocation" {
			continue
		}
		if item.Kind != "evidence" || item.ExecutionScope != "node" {
			t.Fatalf("preallocation execution = %s/%s, want evidence/node", item.Kind, item.ExecutionScope)
		}
		text := item.EvidenceSource + " " + strings.Join(item.Notes, " ")
		if !strings.Contains(text, "需单独发起") || strings.Contains(text, "等待节点回传") {
			t.Fatalf("preallocation copy does not describe an explicit independent run: %q", text)
		}
		return
	}
	t.Fatal("preallocation criterion not found")
}
