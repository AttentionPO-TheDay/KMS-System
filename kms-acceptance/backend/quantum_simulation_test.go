package main

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestQuantumSecurityLive(t *testing.T) {
	if os.Getenv("KMS_QUANTUM_LIVE") != "1" {
		t.Skip("explicit local evaluator and gateway required")
	}
	for _, id := range []string{"quantum-lwe-usvp", "quantum-lwe-bdd", "quantum-lwe-dual"} {
		t.Run(id, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
			defer cancel()
			r := (&server{}).executeSecurityRunContext(ctx, id)
			if dir := os.Getenv("KMS_QUANTUM_EVIDENCE_DIR"); dir != "" {
				body, _ := json.MarshalIndent(r, "", "  ")
				if err := os.WriteFile(filepath.Join(dir, id+"-run.json"), body, 0600); err != nil {
					t.Fatal(err)
				}
			}
			if r.Status != "completed" || r.Verdict != "evaluated" || r.Passed || !r.LegalControlPassed || !validQuantumEvidence(id, r.QuantumEvidence) {
				t.Fatalf("quantum execution failed: %s / %s / %s", r.Status, r.Summary, r.Error)
			}
			t.Log(r.Summary)
		})
	}
}

func testQuantumEvidence() QuantumEvidence {
	circuit := json.RawMessage(`{"verified":true,"qubits":8,"searchSpace":256,"shots":256,"target":"10110100","recovered":"10110100","norm":1,"successProbability":0.999947,"baselineProbability":0.00390625}`)
	e := QuantumEvidence{Version: 1, CaseID: "quantum-lwe-usvp", Model: "primal_usvp", Name: "test", RecordedAt: "2026-10-22T00:00:00Z",
		DurationMs: 1, EstimatorCommit: estimatorCommit, SageVersion: "test", CostModel: "ADPS16(mode=quantum): Core-SVP reduction cost 2^(0.265*beta)",
		Circuit: circuit, EvaluationComplete: true, Scope: "fixture"}
	for _, n := range []int{512, 768, 1024} {
		e.Estimates = append(e.Estimates, QuantumCost{Variant: n, N: n, M: n, Q: 3329, Log2Rop: 100, Beta: 400,
			RawCost: "fixture", SecretDistribution: "fixture", ErrorDistribution: "fixture"})
	}
	return e
}

func TestQuantumEvidenceRejectsClaimsAndIncompleteModels(t *testing.T) {
	if !validQuantumEvidence("quantum-lwe-usvp", func() *QuantumEvidence { e := testQuantumEvidence(); return &e }()) {
		t.Fatal("complete fixture rejected")
	}
	for name, mutate := range map[string]func(*QuantumEvidence){
		"acceptance-claim": func(e *QuantumEvidence) { e.AcceptancePassed = true },
		"wrong-model":      func(e *QuantumEvidence) { e.Model = "dual" },
		"wrong-revision":   func(e *QuantumEvidence) { e.EstimatorCommit = "unreviewed" },
		"missing-variant":  func(e *QuantumEvidence) { e.Estimates = e.Estimates[:2] },
		"duplicate":        func(e *QuantumEvidence) { e.Estimates[1] = e.Estimates[0] },
		"non-finite":       func(e *QuantumEvidence) { e.Estimates[0].Log2Rop = math.Inf(1) },
		"not-complete":     func(e *QuantumEvidence) { e.EvaluationComplete = false },
		"fake-circuit":     func(e *QuantumEvidence) { e.Circuit = json.RawMessage(`{"verified":true}`) },
	} {
		t.Run(name, func(t *testing.T) {
			e := testQuantumEvidence()
			mutate(&e)
			if validQuantumEvidence("quantum-lwe-usvp", &e) {
				t.Fatal("untrustworthy evidence accepted")
			}
		})
	}
}
