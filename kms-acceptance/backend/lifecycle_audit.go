package main

// Acceptance-only metadata snapshots. Reads never mutate keys or resubmit jobs.
import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
)

type lifecycleRow struct {
	KeyID   int64                 `json:"keyId"`
	Before  internalVerifyRecord  `json:"before"`
	After   *internalVerifyRecord `json:"after,omitempty"`
	Outcome string                `json:"outcome"`
}

type lifecycleBatch struct {
	ID              string   `json:"id"`
	ScenarioID      string   `json:"scenarioId"`
	StartedAt       string   `json:"startedAt"`
	FinishedAt      string   `json:"finishedAt,omitempty"`
	BeforeAt        string   `json:"beforeAt"`
	ObservedAt      string   `json:"observedAt,omitempty"`
	Status          string   `json:"status"`
	Account         string   `json:"account"`
	PoolSize        int      `json:"poolSize"`
	Eligible        int      `json:"eligible"`
	Completed       int      `json:"completed"`
	Pending         int      `json:"pending"`
	Excluded        int      `json:"excluded"`
	Unknown         int      `json:"unknown"`
	CompletionRate  *float64 `json:"completionRate"`
	SuccessfulTPS   float64  `json:"successfulTps"`
	TargetTPS       float64  `json:"targetTps"`
	HTTPRequests    int64    `json:"httpRequests"`
	HTTPErrors      int64    `json:"httpErrors"`
	SocketErrors    int64    `json:"socketErrors"`
	Threads         int      `json:"threads"`
	Connections     int      `json:"connections"`
	DurationSeconds int      `json:"durationSeconds"`
	Reason          string   `json:"reason,omitempty"`
	Error           string   `json:"error,omitempty"`
}

type lifecycleArchive struct {
	Owner    string         `json:"owner"`
	Revision int64          `json:"revision"`
	Phase    string         `json:"phase"`
	Batch    lifecycleBatch `json:"batch"`
}

func lifecycleScenario(id string) bool {
	return id == "update-tps" || id == "revoke-tps" || id == "revoke-rate"
}

func lifecycleOwner(session string) string { return fmt.Sprintf("%x", sha256.Sum256([]byte(session))) }

func (s *server) auditDirectory() string { return filepath.Join(s.dataDir, "lifecycle-audit") }

func writeAuditJSON(path string, value interface{}) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".audit-*")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if _, err = f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return os.Rename(name, path)
}

func (s *server) saveLifecycleAudit(archive lifecycleArchive, rows []lifecycleRow) error {
	if !demoRunPath.MatchString("/api/runs/" + archive.Batch.ID) {
		return fmt.Errorf("invalid run id")
	}
	dir := s.auditDirectory()
	// Phase rows are immutable. Commit the small index only after the rows exist.
	if err := writeAuditJSON(filepath.Join(dir, archive.Batch.ID+"-"+archive.Phase+".json"), rows); err != nil {
		return err
	}
	return writeAuditJSON(filepath.Join(dir, archive.Batch.ID+".summary.json"), archive)
}

func (s *server) captureLifecycle(ctx context.Context, ids []int64) (map[int64]internalVerifyRecord, error) {
	records := make(map[int64]internalVerifyRecord, len(ids))
	for start := 0; start < len(ids); start += 200 {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		end := start + 200
		if end > len(ids) {
			end = len(ids)
		}
		items, err := s.fetchLifecycleStatusesContext(ctx, ids[start:end])
		if err != nil {
			return nil, err
		}
		requested := make(map[int64]bool, end-start)
		for _, id := range ids[start:end] {
			requested[id] = true
		}
		for _, item := range items {
			if !requested[item.KeyID] {
				return nil, fmt.Errorf("unexpected key identity in status response")
			}
			if _, exists := records[item.KeyID]; exists {
				return nil, fmt.Errorf("duplicate key identity in status response")
			}
			if item.Exists && (item.UserName != s.cfg.AcceptanceUser || item.KeyDomain != "acceptance" || item.Version == nil) {
				return nil, fmt.Errorf("acceptance metadata incomplete or ownership mismatch; update lifecycle Java metadata endpoint")
			}
			records[item.KeyID] = item
		}
		for _, id := range ids[start:end] {
			if _, ok := records[id]; !ok {
				return nil, fmt.Errorf("missing key identity in status response")
			}
		}
	}
	return records, nil
}

func (s *server) beginLifecycleAudit(ctx context.Context, scenario Scenario, run RunResult, session string, revision int64) (*lifecycleArchive, []lifecycleRow, error) {
	if !lifecycleScenario(scenario.ID) {
		return nil, nil, nil
	}
	records, err := s.captureLifecycle(ctx, scenario.PreparedKeyIDs)
	if err != nil {
		return nil, nil, err
	}
	archive := &lifecycleArchive{Owner: lifecycleOwner(session), Revision: revision, Phase: "before", Batch: lifecycleBatch{
		ID: run.ID, ScenarioID: scenario.ID, StartedAt: run.StartedAt, BeforeAt: time.Now().Format(time.RFC3339),
		Status: "running", Account: s.cfg.AcceptanceUser, PoolSize: len(scenario.PreparedKeyIDs), TargetTPS: scenario.TargetTPS,
		Threads: scenario.Threads, Connections: scenario.Connections, DurationSeconds: scenario.DurationSeconds,
		Reason: "异常回收速率使用验收专用密钥进行回收，不代表系统真实检测到泄漏。"}}
	rows := make([]lifecycleRow, 0, len(scenario.PreparedKeyIDs))
	for _, id := range scenario.PreparedKeyIDs {
		row := lifecycleRow{KeyID: id, Before: records[id], Outcome: "UNVERIFIED"}
		if !row.Before.Exists || row.Before.Status != "0" {
			row.Outcome = "EXCLUDED"
			archive.Batch.Excluded++
		} else {
			archive.Batch.Eligible++
			archive.Batch.Unknown++
		}
		rows = append(rows, row)
	}
	if err = s.saveLifecycleAudit(*archive, rows); err != nil {
		return nil, nil, err
	}
	return archive, rows, nil
}

func auditOutcome(id string, before internalVerifyRecord, after *internalVerifyRecord) string {
	if !before.Exists || before.Status != "0" {
		return "EXCLUDED"
	}
	if after == nil {
		return "UNVERIFIED"
	}
	if !after.Exists {
		return "MISSING"
	}
	if id == "update-tps" {
		if before.Version != nil && after.Version != nil && *after.Version > *before.Version {
			return "COMPLETED"
		}
	} else if after.Status == "3" {
		return "COMPLETED"
	}
	return "PENDING"
}

func summarizeAudit(archive *lifecycleArchive, rows []lifecycleRow, records map[int64]internalVerifyRecord) {
	b := &archive.Batch
	b.Completed, b.Pending, b.Unknown = 0, 0, 0
	for i := range rows {
		row := &rows[i]
		if record, ok := records[row.KeyID]; ok {
			copy := record
			row.After = &copy
		}
		row.Outcome = auditOutcome(b.ScenarioID, row.Before, row.After)
		switch row.Outcome {
		case "COMPLETED":
			b.Completed++
		case "PENDING":
			b.Pending++
		case "UNVERIFIED", "MISSING":
			b.Unknown++
		}
	}
	b.CompletionRate = nil
	if b.Eligible > 0 && b.Unknown == 0 {
		rate := float64(b.Completed) / float64(b.Eligible) * 100
		b.CompletionRate = &rate
	}
}

func (s *server) finishLifecycleAudit(ctx context.Context, archive *lifecycleArchive, rows []lifecycleRow, result RunResult) error {
	if archive == nil {
		return nil
	}
	b := &archive.Batch
	// Completion remains provisional until the Demo authority/lease is validated.
	b.Status, b.FinishedAt = "verifying", ""
	b.SuccessfulTPS, b.HTTPRequests = result.Summary.SuccessfulRequestsPerSec, result.Summary.TotalRequests
	b.HTTPErrors, b.SocketErrors = result.Summary.Non2xxResponses, result.Summary.SocketErrors
	ids := make([]int64, len(rows))
	for i, row := range rows {
		ids[i] = row.KeyID
	}
	deadline := time.Now().Add(time.Duration(s.cfg.VerifyWaitSeconds) * time.Second)
	for {
		records, err := s.captureLifecycle(ctx, ids)
		if err != nil {
			b.Error = "状态核验不可用，不能将接口成功视为实际完成"
			b.CompletionRate = nil
			break
		}
		b.ObservedAt = time.Now().Format(time.RFC3339)
		summarizeAudit(archive, rows, records)
		if b.Completed >= b.Eligible || time.Now().After(deadline) || result.Status == "cancelled" {
			break
		}
		select {
		case <-ctx.Done():
			b.Error = "状态核验被取消或超时"
			b.CompletionRate = nil
		case <-time.After(2 * time.Second):
		}
		if ctx.Err() != nil {
			break
		}
	}
	archive.Phase = "final"
	return s.saveLifecycleAudit(*archive, rows)
}

func auditPage(c *fiber.Ctx) (int, int, error) {
	page, e1 := strconv.Atoi(c.Query("page", "1"))
	size, e2 := strconv.Atoi(c.Query("pageSize", "20"))
	if e1 != nil || e2 != nil || page < 1 || size < 1 || size > 100 {
		return 0, 0, fmt.Errorf("invalid pagination")
	}
	return page, size, nil
}

func applyLifecycleAuditResult(scenario Scenario, archive *lifecycleArchive, result RunResult) RunResult {
	if archive == nil || (scenario.ID != "update-tps" && scenario.ID != "revoke-rate") {
		return result
	}
	b := archive.Batch
	check := MetricCheck{Kind: scenario.MetricKind, Target: scenario.MetricTarget, Operator: scenario.MetricOperator,
		Enforced: true, Source: "acceptance-lifecycle-snapshots", ReportedAt: b.ObservedAt,
		Message: fmt.Sprintf("初始有效池实际完成 %d/%d；排除初始无效 %d 把", b.Completed, b.Eligible, b.Excluded)}
	if b.CompletionRate != nil && b.Error == "" {
		check.Value = *b.CompletionRate
		check.Collected = true
		check.Passed = compareThreshold(check.Value, check.Operator, check.Target)
	} else {
		check.Message = "最终状态不可核定，不能将接口成功视为实际完成"
	}
	result.MetricCheck = check
	if result.Status == "passed" || result.Status == "failed_threshold" {
		if result.PassedTPS && check.Collected && check.Passed {
			result.Status = "passed"
		} else {
			result.Status = "failed_threshold"
		}
	}
	return result
}

func (g *demoGuard) readLifecycleAudit(c *fiber.Ctx, session string, revision int64) error {
	page, size, err := auditPage(c)
	if err != nil {
		return c.Status(400).JSON(fiber.Map{"message": "页码无效，每页最多 100 条"})
	}
	owner := lifecycleOwner(session)
	dir := g.server.auditDirectory()
	id := strings.TrimPrefix(c.Path(), "/api/acceptance/lifecycle/")
	if c.Path() != "/api/acceptance/lifecycle" {
		var archive lifecycleArchive
		data, err := os.ReadFile(filepath.Join(dir, id+".summary.json"))
		if os.IsNotExist(err) {
			return c.Status(404).JSON(fiber.Map{"message": "批次不存在或不属于当前会话"})
		}
		if err != nil || json.Unmarshal(data, &archive) != nil {
			return c.Status(503).JSON(fiber.Map{"message": "批次记录不可用"})
		}
		if archive.Owner != owner || archive.Revision != revision {
			return c.Status(404).JSON(fiber.Map{"message": "批次不存在或不属于当前会话"})
		}
		if archive.Phase != "before" && archive.Phase != "final" {
			return c.SendStatus(503)
		}
		var rows []lifecycleRow
		data, err = os.ReadFile(filepath.Join(dir, id+"-"+archive.Phase+".json"))
		if err != nil || json.Unmarshal(data, &rows) != nil {
			return c.Status(503).JSON(fiber.Map{"message": "密钥快照不可用"})
		}
		q, outcome := c.Query("q"), c.Query("outcome")
		if len(q) > 64 {
			return c.SendStatus(400)
		}
		filtered := make([]lifecycleRow, 0)
		for _, row := range rows {
			if (q == "" || strings.Contains(strconv.FormatInt(row.KeyID, 10), q)) && (outcome == "" || row.Outcome == outcome) {
				filtered = append(filtered, row)
			}
		}
		total := len(filtered)
		last := (total + size - 1) / size
		if last < 1 {
			last = 1
		}
		if page > last {
			page = last
		}
		start := (page - 1) * size
		end := start + size
		if end > total {
			end = total
		}
		return c.JSON(fiber.Map{"batch": archive.Batch, "items": filtered[start:end], "total": total, "page": page, "pageSize": size})
	}
	files, err := filepath.Glob(filepath.Join(dir, "*.summary.json"))
	if err != nil {
		return c.SendStatus(503)
	}
	list := make([]lifecycleBatch, 0)
	for _, file := range files {
		var archive lifecycleArchive
		data, err := os.ReadFile(file)
		if err != nil || json.Unmarshal(data, &archive) != nil {
			return c.Status(503).JSON(fiber.Map{"message": "归档记录不可用"})
		}
		if archive.Owner == owner && archive.Revision == revision && (c.Query("scenario") == "" || archive.Batch.ScenarioID == c.Query("scenario")) {
			list = append(list, archive.Batch)
		}
	}
	sort.Slice(list, func(i, j int) bool { return list[i].StartedAt > list[j].StartedAt })
	total := len(list)
	last := (total + size - 1) / size
	if last < 1 {
		last = 1
	}
	if page > last {
		page = last
	}
	start := (page - 1) * size
	end := start + size
	if end > total {
		end = total
	}
	return c.JSON(fiber.Map{"items": list[start:end], "total": total, "page": page, "pageSize": size})
}
