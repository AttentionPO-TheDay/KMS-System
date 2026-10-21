package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"time"
)

const abnormalSource = "node-auto-revoke-isolated-mysql"

func abnormalScenario(id string) bool { return id == "revoke-tps" || id == "revoke-rate" }

type abnormalRule struct {
	Rule     string `json:"rule"`
	Injected int    `json:"injected"`
	Detected int    `json:"detected"`
	Revoked  int    `json:"revoked"`
}

type abnormalBatch struct {
	BatchID         string  `json:"batchId"`
	Attempted       int     `json:"attempted"`
	Revoked         int     `json:"revoked"`
	PoolRevoked     int     `json:"poolRevoked"`
	SessionsRevoked int     `json:"sessionsRevoked"`
	ElapsedMs       float64 `json:"elapsedMs"`
}

type abnormalRow struct {
	KeyID        int64  `json:"keyId"`
	NodeID       string `json:"nodeId"`
	Algorithm    string `json:"algorithm"`
	Rule         string `json:"rule"`
	DetectedRule string `json:"detectedRule"`
	Abnormal     bool   `json:"abnormal"`
	Attempted    bool   `json:"attempted"`
	BeforeStatus string `json:"beforeStatus"`
	AfterStatus  string `json:"afterStatus"`
	Action       string `json:"action"`
	Passed       bool   `json:"passed"`
}

type abnormalEvidence struct {
	Version         int             `json:"version"`
	Source          string          `json:"source"`
	Isolated        bool            `json:"isolated"`
	CleanupComplete bool            `json:"cleanupComplete"`
	BatchID         string          `json:"batchId"`
	BatchLimit      int             `json:"batchLimit"`
	Batches         []abnormalBatch `json:"batches"`
	Injected        int             `json:"injected"`
	Attempted       int             `json:"attempted"`
	Detected        int             `json:"detected"`
	Revoked         int             `json:"revoked"`
	Controls        int             `json:"controls"`
	ControlsPassed  int             `json:"controlsPassed"`
	PoolRevoked     int             `json:"poolRevoked"`
	SessionsRevoked int             `json:"sessionsRevoked"`
	Invalidations   int             `json:"invalidations"`
	ElapsedMs       float64         `json:"elapsedMs"`
	TotalMs         float64         `json:"totalMs"`
	BeforeAt        string          `json:"beforeAt"`
	ObservedAt      string          `json:"observedAt"`
	Passed          bool            `json:"passed"`
	Rules           []abnormalRule  `json:"rules"`
	Rows            []abnormalRow   `json:"rows,omitempty"`
}

func validateAbnormalEvidence(e *abnormalEvidence) error {
	if e == nil || e.Version != 2 || e.Source != abnormalSource || !e.Isolated || !e.CleanupComplete ||
		e.BatchID == "" || e.Injected != 6000 || e.BatchLimit != 5000 || len(e.Batches) == 0 || len(e.Batches) > e.Injected+1 ||
		e.Attempted < 0 || e.Attempted > e.Injected || e.Controls != 4 || len(e.Rows) != e.Injected+e.Controls ||
		e.ElapsedMs <= 0 || math.IsNaN(e.ElapsedMs) || math.IsInf(e.ElapsedMs, 0) ||
		e.TotalMs < e.ElapsedMs || e.BeforeAt == "" || e.ObservedAt == "" {
		return fmt.Errorf("异常样本、隔离清理或测量证据不完整")
	}
	batchIDs := map[string]bool{}
	batchRevoked, batchPool, batchSessions, batchAttempted, batchMs := 0, 0, 0, 0, 0.0
	for _, batch := range e.Batches {
		if batch.Revoked < 0 || batch.Revoked > batch.Attempted || batch.Attempted > e.BatchLimit || batch.Attempted > e.Attempted || batch.PoolRevoked < 0 || batch.SessionsRevoked < 0 ||
			batch.ElapsedMs < 0 || math.IsNaN(batch.ElapsedMs) || math.IsInf(batch.ElapsedMs, 0) ||
			(batch.Revoked > 0 && (batch.BatchID == "" || batchIDs[batch.BatchID])) {
			return fmt.Errorf("跨批次扫描证据无效")
		}
		batchIDs[batch.BatchID] = true
		batchRevoked += batch.Revoked
		batchAttempted += batch.Attempted
		batchPool += batch.PoolRevoked
		batchSessions += batch.SessionsRevoked
		batchMs += batch.ElapsedMs
	}
	if batchRevoked != e.Revoked || batchPool != e.PoolRevoked || batchSessions != e.SessionsRevoked || batchMs > e.ElapsedMs || batchAttempted < e.Attempted {
		return fmt.Errorf("跨批次扫描与汇总证据不一致")
	}
	rules := map[string]*abnormalRule{}
	for _, name := range []string{"PUBLIC_KEY_MISSING", "PUBLIC_KEY_HASH_MISSING", "PUBLIC_KEY_HASH_MISMATCH"} {
		rules[name] = &abnormalRule{Rule: name}
	}
	seen := map[int64]bool{}
	detected, revoked, controls, injected, attempted, controlCount, warningCount := 0, 0, 0, 0, 0, 0, 0
	for _, row := range e.Rows {
		if row.KeyID <= 0 || seen[row.KeyID] || row.NodeID == "" || row.BeforeStatus != "ACTIVE" {
			return fmt.Errorf("异常回收逐钥快照缺失或重复")
		}
		seen[row.KeyID] = true
		passed := false
		if row.Abnormal {
			injected++
			if row.Attempted {
				attempted++
			}
			rule, ok := rules[row.Rule]
			if !ok {
				return fmt.Errorf("未知异常规则")
			}
			rule.Injected++
			if row.DetectedRule == row.Rule {
				rule.Detected++
				detected++
				if row.AfterStatus == "REVOKED" && row.Action == "AUTO_REVOKED" && row.Attempted {
					rule.Revoked++
					revoked++
					passed = true
				}
			}
		} else {
			if row.Attempted {
				return fmt.Errorf("正常或仅告警对照不得进入自动回收候选集")
			}
			controlCount++
			if row.Rule == "MATERIALIZED_PUBLIC_KEY_MISMATCH" {
				warningCount++
			}
			passed = row.AfterStatus == "ACTIVE" && ((row.Rule == "" && row.DetectedRule == "" && row.Action == "") ||
				(row.Rule == "MATERIALIZED_PUBLIC_KEY_MISMATCH" && row.DetectedRule == row.Rule && row.Action == "PENDING_REVIEW"))
			if passed {
				controls++
			}
		}
		if row.Passed != passed {
			return fmt.Errorf("逐钥结果与状态快照不一致")
		}
	}
	if len(e.Rules) != len(rules) {
		return fmt.Errorf("缺少固定异常规则")
	}
	for _, reported := range e.Rules {
		actual, ok := rules[reported.Rule]
		if !ok || actual.Injected == 0 || reported != *actual {
			return fmt.Errorf("异常规则计数与逐钥快照不一致")
		}
		delete(rules, reported.Rule)
	}
	if injected != e.Injected || attempted != e.Attempted || controlCount != e.Controls || warningCount != 1 || e.Detected != detected || e.Revoked != revoked || e.ControlsPassed != controls {
		return fmt.Errorf("汇总与逐钥快照不一致")
	}
	closed := revoked == e.Injected && controls == e.Controls &&
		e.PoolRevoked == e.Injected && e.SessionsRevoked == e.Injected && e.Invalidations == e.Injected
	if e.Passed != closed {
		return fmt.Errorf("回收及依赖失效结论不一致")
	}
	return nil
}

func (s *server) executeAbnormalRevocation(ctx context.Context, scenario Scenario) RunResult {
	result := RunResult{Status: "failed"}
	if s.cfg.AbnormalRevocationURL == "" || s.cfg.GenerateInternalToken == "" {
		result.Error = "异常回收验收内部地址或令牌未配置"
		return result
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.cfg.AbnormalRevocationURL, bytes.NewBufferString("{}"))
	if err != nil {
		result.Error = "异常回收验收地址无效"
		return result
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)
	client := *s.client
	client.Timeout = 90 * time.Second
	response, err := client.Do(req)
	if err != nil {
		result.Error = "异常回收验收服务不可用"
		return result
	}
	defer response.Body.Close()
	var envelope struct {
		Code int               `json:"code"`
		Data *abnormalEvidence `json:"data"`
	}
	if response.StatusCode != http.StatusOK || json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&envelope) != nil || envelope.Code != 200 {
		result.Error = "异常回收验收未返回有效证据"
		return result
	}
	e := envelope.Data
	if err := validateAbnormalEvidence(e); err != nil {
		result.Error = err.Error()
		return result
	}
	result.Abnormal = e
	rate := float64(e.Revoked) * 1000 / e.ElapsedMs
	result.PassedTPS = compareThreshold(rate, scenario.TargetOperator, scenario.TargetTPS)
	result.Summary = RunSummary{TotalRequests: int64(e.Injected), SuccessfulRequestsPerSec: rate,
		RequestsPerSec: float64(e.Injected) * 1000 / e.ElapsedMs, SuccessRate: float64(e.Revoked) * 100 / float64(e.Injected)}
	result.MetricCheck = MetricCheck{Kind: "abnormal_revoke_closure", Value: float64(e.Revoked) * 100 / float64(e.Injected),
		Target: 100, Operator: ">=", Passed: e.Passed, Source: abnormalSource, Collected: true, Enforced: true,
		ReportedAt: e.ObservedAt, Message: fmt.Sprintf("异常 %d 把，检测 %d，回收 %d；对照通过 %d/%d；池项失效 %d，会话失效 %d。",
			e.Injected, e.Detected, e.Revoked, e.ControlsPassed, e.Controls, e.PoolRevoked, e.SessionsRevoked)}
	if scenario.ID == "revoke-rate" {
		result.MetricCheck.Value = 0
		if e.Attempted > 0 {
			result.MetricCheck.Value = float64(e.Revoked) * 100 / float64(e.Attempted)
		}
		result.Summary.TotalRequests = int64(e.Attempted)
		result.Summary.SuccessRate = result.MetricCheck.Value
		result.MetricCheck.Collected = e.Attempted > 0
		result.MetricCheck.Kind = scenario.MetricKind
		result.MetricCheck.Target = scenario.MetricTarget
		result.MetricCheck.Operator = scenario.MetricOperator
		result.MetricCheck.Passed = e.Attempted > 0 && compareThreshold(result.MetricCheck.Value, scenario.MetricOperator, scenario.MetricTarget) &&
			e.ControlsPassed == e.Controls && e.PoolRevoked == e.Revoked && e.SessionsRevoked == e.Revoked && e.Invalidations == e.Revoked
		// Recovery percentage has its own criterion; throughput is reported but is not a pass gate.
		result.PassedTPS = true
		result.MetricCheck.Message = fmt.Sprintf("实际发起回收 %d 把，成功 %d，失败 %d；样本 %d，未发起 %d；对照通过 %d/%d。",
			e.Attempted, e.Revoked, e.Attempted-e.Revoked, e.Injected, e.Injected-e.Attempted, e.ControlsPassed, e.Controls)
		if e.Attempted == 0 {
			result.Error = "未实际发起回收，无法计算回收率"
			return result
		}
	}
	result.Status = "failed_threshold"
	if result.PassedTPS && result.MetricCheck.Passed {
		result.Status = "passed"
	}
	return result
}

func abnormalAudit(run RunResult, e *abnormalEvidence, session string, revision int64) (*lifecycleArchive, []lifecycleRow) {
	denominator := e.Injected
	if run.ScenarioID == "revoke-rate" {
		denominator = e.Attempted
	}
	var rate *float64
	if denominator > 0 {
		value := float64(e.Revoked) * 100 / float64(denominator)
		rate = &value
	}
	archive := &lifecycleArchive{Owner: lifecycleOwner(session), Revision: revision, Phase: "final", Batch: lifecycleBatch{
		ID: run.ID, ScenarioID: run.ScenarioID, StartedAt: run.StartedAt, BeforeAt: e.BeforeAt, ObservedAt: e.ObservedAt,
		EvidenceSource: abnormalSource, Account: "隔离验收临时数据", PoolSize: len(e.Rows), Eligible: denominator,
		Injected: e.Injected, Attempted: e.Attempted, NotAttempted: e.Injected - e.Attempted,
		Completed: e.Revoked, Pending: denominator - e.Revoked, Excluded: e.Controls, CompletionRate: rate,
		SuccessfulTPS: float64(e.Revoked) * 1000 / e.ElapsedMs, TargetTPS: run.TargetTPS,
		Reason: fmt.Sprintf("先注入三类异常，再运行生产检测与自动回收；正常及仅告警对照通过 %d/%d；样本已清理，保留状态快照。", e.ControlsPassed, e.Controls)}}
	rows := make([]lifecycleRow, 0, len(e.Rows))
	for _, row := range e.Rows {
		version := 1
		before := internalVerifyRecord{KeyID: row.KeyID, Exists: true, Status: row.BeforeStatus, Version: &version, KeyDomain: "acceptance"}
		after := before
		after.Status = row.AfterStatus
		after.UpdatedAt = e.ObservedAt
		outcome := "PENDING"
		if row.Abnormal && !row.Attempted {
			outcome = "NOT_ATTEMPTED"
		}
		if row.Passed {
			outcome = "COMPLETED"
		}
		if !row.Abnormal {
			outcome = "CONTROL_FAILED"
			if row.Passed {
				outcome = "CONTROL_PASSED"
			}
		}
		rows = append(rows, lifecycleRow{KeyID: row.KeyID, NodeID: row.NodeID, Algorithm: row.Algorithm, AnomalyRule: row.Rule,
			Action: row.Action, Before: before, After: &after, Outcome: outcome})
	}
	return archive, rows
}
