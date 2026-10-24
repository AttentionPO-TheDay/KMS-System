package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"time"
)

const symmetricSource = "sm4-expired-pool-isolated-mysql"
const symmetricCount = 12000

func symmetricScenario(id string) bool { return id == "symmetric-reclaim-tps" }

type symmetricRow struct {
	KeyID        int64  `json:"keyId"`
	PoolID       string `json:"poolId"`
	KeyIndex     int    `json:"keyIndex"`
	KeyHash      string `json:"keyHash"`
	Algorithm    string `json:"algorithm"`
	Eligible     bool   `json:"eligible"`
	ExpiresAt    string `json:"expiresAt"`
	BeforeStatus string `json:"beforeStatus"`
	AfterStatus  string `json:"afterStatus"`
	Deleted      bool   `json:"deleted"`
}

type symmetricEvidence struct {
	Version          int            `json:"version"`
	Source           string         `json:"source"`
	Isolated         bool           `json:"isolated"`
	CleanupComplete  bool           `json:"cleanupComplete"`
	MaterialVerified bool           `json:"materialVerified"`
	BatchID          string         `json:"batchId"`
	Injected         int            `json:"injected"`
	Reclaimed        int            `json:"reclaimed"`
	Remaining        int            `json:"remaining"`
	Controls         int            `json:"controls"`
	ControlsPassed   int            `json:"controlsPassed"`
	ElapsedMs        float64        `json:"elapsedMs"`
	TotalMs          float64        `json:"totalMs"`
	BeforeAt         string         `json:"beforeAt"`
	ObservedAt       string         `json:"observedAt"`
	Passed           bool           `json:"passed"`
	Rows             []symmetricRow `json:"rows,omitempty"`
}

func validateSymmetricEvidence(e *symmetricEvidence) error {
	if e == nil || e.Version != 1 || e.Source != symmetricSource || !e.Isolated || !e.CleanupComplete || !e.MaterialVerified ||
		e.BatchID == "" || e.Injected != symmetricCount || e.Controls != 4 || len(e.Rows) != symmetricCount+4 ||
		e.ElapsedMs <= 0 || math.IsNaN(e.ElapsedMs) || math.IsInf(e.ElapsedMs, 0) ||
		e.TotalMs < e.ElapsedMs || math.IsNaN(e.TotalMs) || math.IsInf(e.TotalMs, 0) {
		return fmt.Errorf("对称密钥样本、隔离清理或计时证据不完整")
	}
	before, err := time.Parse(time.RFC3339Nano, e.BeforeAt)
	observed, err2 := time.Parse(time.RFC3339Nano, e.ObservedAt)
	if err != nil || err2 != nil || observed.Before(before) {
		return fmt.Errorf("对称密钥快照时间无效")
	}
	ids, hashes, indexes := map[int64]bool{}, map[string]bool{}, map[int]bool{}
	completed, controls := 0, 0
	poolID := e.Rows[0].PoolID
	for _, row := range e.Rows {
		digest, hashErr := hex.DecodeString(row.KeyHash)
		expires, expiryErr := time.Parse(time.RFC3339Nano, row.ExpiresAt)
		if row.KeyID <= 0 || ids[row.KeyID] || hashErr != nil || len(digest) != 32 || hashes[row.KeyHash] ||
			row.KeyIndex < 0 || row.KeyIndex >= symmetricCount+4 || indexes[row.KeyIndex] || row.PoolID == "" || row.PoolID != poolID ||
			row.Algorithm != "sm4" || expiryErr != nil || row.Eligible != (row.KeyIndex < symmetricCount) ||
			row.Deleted != (row.AfterStatus == "DELETED") {
			return fmt.Errorf("对称密钥逐项快照缺失、重复或口径不符")
		}
		ids[row.KeyID], hashes[row.KeyHash], indexes[row.KeyIndex] = true, true, true
		if row.Eligible {
			expected := []string{"READY", "EXPIRED"}[row.KeyIndex%2]
			if expires.After(before) || row.BeforeStatus != expected || (!row.Deleted && row.AfterStatus != row.BeforeStatus) {
				return fmt.Errorf("应回收到期样本的状态或有效期不符")
			}
			if row.Deleted {
				completed++
			}
		} else {
			index := row.KeyIndex - symmetricCount
			if row.BeforeStatus != []string{"READY", "CONSUMED", "REVOKED", "RESERVED"}[index] ||
				(index == 0 && !expires.After(observed)) || (index != 0 && expires.After(before)) {
				return fmt.Errorf("未到期及保留状态对照不完整")
			}
			if !row.Deleted && row.AfterStatus == row.BeforeStatus {
				controls++
			}
		}
	}
	if completed != e.Reclaimed || e.Remaining != e.Injected-completed || controls != e.ControlsPassed ||
		e.Passed != (completed == e.Injected && controls == e.Controls) {
		return fmt.Errorf("对称密钥汇总与逐项回收状态不一致")
	}
	return nil
}

func (s *server) executeSymmetricReclamation(ctx context.Context, scenario Scenario) RunResult {
	result := RunResult{Status: "failed"}
	if s.cfg.SymmetricReclamationURL == "" || s.cfg.GenerateInternalToken == "" {
		result.Error = "对称密钥回收验收内部地址或令牌未配置"
		return result
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.cfg.SymmetricReclamationURL, bytes.NewBufferString("{}"))
	if err != nil {
		result.Error = "对称密钥回收验收地址无效"
		return result
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)
	client := *s.client
	client.Timeout = 90 * time.Second
	response, err := client.Do(req)
	if err != nil {
		result.Error = "对称密钥回收验收服务不可用"
		return result
	}
	defer response.Body.Close()
	var envelope struct {
		Code int                `json:"code"`
		Data *symmetricEvidence `json:"data"`
	}
	if response.StatusCode != http.StatusOK || json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&envelope) != nil || envelope.Code != 200 {
		result.Error = "对称密钥回收未返回有效测量证据"
		return result
	}
	if err := validateSymmetricEvidence(envelope.Data); err != nil {
		result.Error = err.Error()
		return result
	}
	e := envelope.Data
	rate := float64(e.Reclaimed) * 1000 / e.ElapsedMs
	result.Symmetric = e
	result.PassedTPS = compareThreshold(rate, scenario.TargetOperator, scenario.TargetTPS)
	result.Summary = RunSummary{TotalRequests: int64(e.Injected), RequestsPerSec: float64(e.Injected) * 1000 / e.ElapsedMs,
		SuccessfulRequestsPerSec: rate, SuccessRate: float64(e.Reclaimed) * 100 / float64(e.Injected)}
	result.MetricCheck = MetricCheck{Kind: "symmetric_reclamation_closure", Value: float64(e.Reclaimed), Target: symmetricCount,
		Operator: ">=", Passed: e.Passed, Collected: true, Enforced: true, Source: symmetricSource, ReportedAt: e.ObservedAt,
		Message: fmt.Sprintf("到期SM4样本%d条，实际回收%d条，剩余%d条；对照通过%d/%d。", e.Injected, e.Reclaimed, e.Remaining, e.ControlsPassed, e.Controls)}
	result.Status = "failed_threshold"
	if result.PassedTPS && result.MetricCheck.Passed {
		result.Status = "passed"
	}
	return result
}

func symmetricAudit(run RunResult, e *symmetricEvidence, session string, revision int64) (*lifecycleArchive, []lifecycleRow) {
	rate := float64(e.Reclaimed) * 100 / float64(e.Injected)
	archive := &lifecycleArchive{Owner: lifecycleOwner(session), Revision: revision, Phase: "final", Batch: lifecycleBatch{
		ID: run.ID, ScenarioID: run.ScenarioID, StartedAt: run.StartedAt, BeforeAt: e.BeforeAt, ObservedAt: e.ObservedAt,
		EvidenceSource: symmetricSource, Account: "隔离SM4预分配池", PoolSize: len(e.Rows), Eligible: e.Injected, Injected: e.Injected,
		Completed: e.Reclaimed, Pending: e.Remaining, Excluded: e.Controls, CompletionRate: &rate,
		SuccessfulTPS: float64(e.Reclaimed) * 1000 / e.ElapsedMs, ElapsedMs: e.ElapsedMs, TargetTPS: run.TargetTPS,
		Reason: "到期SM4保护包实际删除；未到期及CONSUMED、REVOKED、RESERVED对照保留。样本已清理，保留逐项快照。"}}
	rows := make([]lifecycleRow, 0, len(e.Rows))
	for _, row := range e.Rows {
		before := internalVerifyRecord{KeyID: row.KeyID, Exists: true, Status: row.BeforeStatus, KeyDomain: "acceptance"}
		after := before
		after.Exists, after.Status, after.UpdatedAt = !row.Deleted, row.AfterStatus, e.ObservedAt
		outcome := "PENDING"
		if row.Eligible && row.Deleted {
			outcome = "COMPLETED"
		}
		if !row.Eligible {
			outcome = "CONTROL_FAILED"
			if !row.Deleted && row.AfterStatus == row.BeforeStatus {
				outcome = "CONTROL_PASSED"
			}
		}
		rows = append(rows, lifecycleRow{KeyID: row.KeyID, Algorithm: "SM4", PoolID: row.PoolID, KeyHash: row.KeyHash,
			ExpiresAt: row.ExpiresAt, Before: before, After: &after, Outcome: outcome})
	}
	return archive, rows
}
