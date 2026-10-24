package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"strings"
	"time"
)

const estimatorCommit = "e4333d9bf9ef42fd8a29651b0c559fba7ce0d834"

var quantumModels = map[string]string{
	"quantum-lwe-usvp": "primal_usvp", "quantum-lwe-bdd": "primal_bdd", "quantum-lwe-dual": "dual",
}

// Preserve the full, public simulation artifact without persisting business key material.
type QuantumEvidence struct {
	Version            int             `json:"version"`
	CaseID             string          `json:"caseId"`
	Model              string          `json:"model"`
	Name               string          `json:"name"`
	RecordedAt         string          `json:"recordedAt"`
	DurationMs         float64         `json:"durationMs"`
	EstimatorCommit    string          `json:"estimatorCommit"`
	SageVersion        string          `json:"sageVersion"`
	CostModel          string          `json:"costModel"`
	Circuit            json.RawMessage `json:"circuit"`
	Estimates          []QuantumCost   `json:"estimates"`
	EvaluationComplete bool            `json:"evaluationComplete"`
	AcceptancePassed   bool            `json:"acceptancePassed"`
	Scope              string          `json:"scope"`
	References         []string        `json:"references"`
}

type QuantumCost struct {
	Variant            int     `json:"variant"`
	N                  int     `json:"n"`
	Q                  int     `json:"q"`
	M                  int     `json:"m"`
	SecretDistribution string  `json:"secretDistribution"`
	ErrorDistribution  string  `json:"errorDistribution"`
	Log2Rop            float64 `json:"log2Rop"`
	Beta               int     `json:"beta"`
	RawCost            string  `json:"rawCost"`
	DurationMs         float64 `json:"durationMs"`
}

func validQuantumEvidence(caseID string, e *QuantumEvidence) bool {
	model := quantumModels[caseID]
	if e == nil || model == "" || e.Version != 1 || e.CaseID != caseID || e.Model != model ||
		e.EstimatorCommit != estimatorCommit || e.CostModel != "ADPS16(mode=quantum): Core-SVP reduction cost 2^(0.265*beta)" ||
		e.SageVersion == "" || e.Scope == "" || !e.EvaluationComplete || e.AcceptancePassed || len(e.Estimates) != 3 ||
		e.DurationMs <= 0 || math.IsNaN(e.DurationMs) || math.IsInf(e.DurationMs, 0) {
		return false
	}
	if _, err := time.Parse(time.RFC3339Nano, e.RecordedAt); err != nil {
		return false
	}
	var circuit struct {
		Verified            bool    `json:"verified"`
		Qubits              int     `json:"qubits"`
		SearchSpace         int     `json:"searchSpace"`
		Shots               int     `json:"shots"`
		Target              string  `json:"target"`
		Recovered           string  `json:"recovered"`
		Norm                float64 `json:"norm"`
		SuccessProbability  float64 `json:"successProbability"`
		BaselineProbability float64 `json:"baselineProbability"`
	}
	if json.Unmarshal(e.Circuit, &circuit) != nil || !circuit.Verified || circuit.Qubits != 8 ||
		circuit.SearchSpace != 256 || circuit.Shots != 256 || len(circuit.Target) != 8 || circuit.Recovered != circuit.Target ||
		math.Abs(circuit.Norm-1) > 1e-9 || circuit.SuccessProbability < .99 || circuit.SuccessProbability > 1 ||
		math.Abs(circuit.BaselineProbability-1.0/256) > 1e-9 {
		return false
	}
	for i, cost := range e.Estimates {
		n := []int{512, 768, 1024}[i]
		if cost.Variant != n || cost.N != n || cost.M != n || cost.Q != 3329 ||
			cost.Log2Rop <= 0 || math.IsNaN(cost.Log2Rop) || math.IsInf(cost.Log2Rop, 0) || cost.Beta < 2 ||
			cost.RawCost == "" || cost.SecretDistribution == "" || cost.ErrorDistribution == "" {
			return false
		}
	}
	return true
}

func (s *server) executeQuantumSecurity(ctx context.Context, caseID string) SecurityRunResult {
	// Use the deployed native library and its independent public vectors for the
	// legal-business control, separately from the mathematical attack simulation.
	controlCtx := context.WithValue(ctx, securityProgressKey{}, func(snapshot SecurityRunResult) {
		snapshot.CaseID, snapshot.Passed, snapshot.EvidenceVersion = caseID, false, 4
		snapshot.Status = "running"
		if report, ok := ctx.Value(securityProgressKey{}).(func(SecurityRunResult)); ok {
			report(snapshot)
		}
	})
	r := s.executeSystemSecurity(controlCtx, "pq-parameter-downgrade")
	controlOK := r.Passed && r.LegalControlPassed && validAlgorithmEvidence("pq-parameter-downgrade", r.AlgorithmEvidence)
	r.CaseID, r.EvidenceVersion, r.Passed, r.Verdict = caseID, 4, false, "insufficient_evidence"
	if !controlOK {
		detail := r.Error
		if detail == "" {
			detail = r.Summary
		}
		r.Status, r.Error = "error", "部署算法正常业务对照未通过，未执行量子评估："+detail
		return r
	}
	r.Stage = "运行弱参数量子电路与实际Kyber参数格攻击成本评估"
	r.Status = "running"
	if report, ok := ctx.Value(securityProgressKey{}).(func(SecurityRunResult)); ok {
		report(r)
	}
	fail := func(message string) SecurityRunResult {
		r.Status, r.Error, r.Summary = "error", message, "未取得完整量子仿真证据"
		return r
	}
	url := strings.TrimSpace(envOrDefault("ACCEPTANCE_QUANTUM_URL", "http://quantum-evaluator:8800/evaluate"))
	token := envOrDefault("ACCEPTANCE_INTERNAL_TOKEN", s.cfg.GenerateInternalToken)
	if token == "" {
		return fail("量子评估服务凭据未配置")
	}
	body, _ := json.Marshal(map[string]string{"caseId": caseID})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fail("量子评估地址无效")
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", token)
	client := &http.Client{Timeout: 105 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	started := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		return fail("量子评估服务未取得响应或任务已停止")
	}
	defer resp.Body.Close()
	r.Requests = append(r.Requests, SecurityRequestTrace{Name: "量子电路仿真及格攻击成本评估", Method: http.MethodPost, URL: "/evaluate",
		StatusCode: resp.StatusCode, Outcome: "received", Message: "固定模型评估器响应，不包含业务密钥", RecordedAt: time.Now().Format(time.RFC3339Nano), DurationMs: time.Since(started).Milliseconds()})
	var evidence QuantumEvidence
	if resp.StatusCode != 200 || json.NewDecoder(io.LimitReader(resp.Body, 256<<10)).Decode(&evidence) != nil || !validQuantumEvidence(caseID, &evidence) {
		return fail("量子评估失败或返回证据不完整")
	}
	r.QuantumEvidence = &evidence
	after := s.executeSystemSecurity(controlCtx, "pq-parameter-downgrade")
	r.Requests = append(r.Requests, after.Requests...)
	r.LegalControlPassed = after.Passed && after.LegalControlPassed && validAlgorithmEvidence("pq-parameter-downgrade", after.AlgorithmEvidence)
	if !r.LegalControlPassed {
		return fail("仿真后部署算法正常业务对照未通过")
	}
	r.AlgorithmEvidence = after.AlgorithmEvidence
	r.Status, r.Verdict, r.Stage = "completed", "evaluated", "仿真与参数评估完成"
	r.Summary = fmt.Sprintf("%s完成；8量子位弱样本搜索验证有效；3组Kyber参数成本已计算；部署原生KYBER正常对照通过。", evidence.Name)
	r.Notes = []string{"仿真完成不等于生产参数抗攻击指标达标。三种格攻击模型及其量子成本假设需由第三方确认验收口径。"}
	return r
}
