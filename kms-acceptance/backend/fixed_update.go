package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const fixedUpdateCount = 6000

type fixedUpdateEvidence struct {
	Version      int     `json:"version"`
	Selected     int     `json:"selected"`
	Submitted    int     `json:"submitted"`
	Accepted     int     `json:"accepted"`
	Duplicates   int     `json:"duplicates"`
	Rejected     int     `json:"rejected"`
	Completed    int     `json:"completed"`
	Verified     bool    `json:"verified"`
	StartedAt    string  `json:"startedAt"`
	SubmissionMs float64 `json:"submissionMs"`
	ElapsedMs    float64 `json:"elapsedMs"`
	AcceptedTPS  float64 `json:"acceptedTps"`
	SourceRunID  string  `json:"sourceRunId,omitempty"`
}

func (g *demoGuard) latestGeneration(session string, revision int64) (string, time.Time) {
	g.mu.RLock()
	defer g.mu.RUnlock()
	for i := len(g.jobOrder) - 1; i >= 0; i-- {
		job := g.jobs[g.jobOrder[i]]
		if job.session == session && job.revision == revision && job.result.ScenarioID == "generate-tps" &&
			(job.result.Status == "passed" || job.result.Status == "failed_threshold") && job.result.Summary.TotalRequests > 0 {
			started, _ := time.Parse(time.RFC3339, job.result.StartedAt)
			return job.result.ID, started
		}
	}
	return "", time.Time{}
}

func (s *server) executeFixedUpdate(ctx context.Context, scenario Scenario) RunResult {
	result := RunResult{Status: "failed"}
	seen := map[int64]bool{}
	for _, id := range scenario.PreparedKeyIDs {
		if id <= 0 || seen[id] {
			result.Error = "更新测试需要 6000 把不同的有效密钥"
			return result
		}
		seen[id] = true
	}
	if len(seen) != fixedUpdateCount {
		result.Error = "更新测试需要恰好 6000 把已生成密钥"
		return result
	}
	workers := max(1, min(scenario.Connections, 100))
	client := *s.client
	if client.Transport == nil {
		transport := http.DefaultTransport.(*http.Transport).Clone()
		transport.MaxIdleConnsPerHost, transport.MaxConnsPerHost = workers, workers
		client.Transport = transport
		defer transport.CloseIdleConnections()
	}
	e := &fixedUpdateEvidence{Version: 2, Selected: len(seen), SourceRunID: scenario.SourceRunID}
	started := time.Now()
	e.StartedAt = started.Format(time.RFC3339Nano)
	batchID := s.nextID()
	var next atomic.Int64
	var mu sync.Mutex
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				i := int(next.Add(1) - 1)
				if i >= len(scenario.PreparedKeyIDs) || ctx.Err() != nil {
					return
				}
				id := scenario.PreparedKeyIDs[i]
				body := strings.Replace(scenario.BodyTemplate, keyIDPlaceholder, strconv.FormatInt(id, 10), 1)
				req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(scenario.BaseURL, "/")+scenario.Path, bytes.NewBufferString(body))
				if err != nil {
					mu.Lock()
					e.Rejected++
					mu.Unlock()
					continue
				}
				for name, value := range scenario.Headers {
					req.Header.Set(name, value)
				}
				req.Header.Set("Content-Type", "application/json")
				// A new run may legitimately update the same key again. Within a run
				// each key is submitted exactly once, with a stable idempotency key.
				req.Header.Set("Idempotency-Key", fmt.Sprintf("acceptance-update:%s:%d", batchID, id))
				mu.Lock()
				e.Submitted++
				mu.Unlock()
				response, err := client.Do(req)
				var payload struct {
					Code   int    `json:"code"`
					Status string `json:"status"`
				}
				accepted, duplicate := false, false
				if err == nil {
					decodeErr := json.NewDecoder(io.LimitReader(response.Body, 4096)).Decode(&payload)
					accepted = decodeErr == nil && response.StatusCode == 200 && payload.Code == 200 && payload.Status == "accepted"
					duplicate = payload.Status == "duplicate"
					response.Body.Close()
				}
				mu.Lock()
				if accepted {
					e.Accepted++
				} else if duplicate {
					e.Duplicates++
				} else {
					e.Rejected++
				}
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	e.SubmissionMs = float64(time.Since(started)) / float64(time.Millisecond)
	e.AcceptedTPS = float64(e.Accepted) * 1000 / e.SubmissionMs
	result.FixedUpdate = e
	result.Summary = RunSummary{TotalRequests: int64(e.Submitted), RequestsPerSec: float64(e.Submitted) * 1000 / e.SubmissionMs}
	result.Status = "failed_threshold" // Final version snapshots decide completion and throughput.
	if ctx.Err() != nil {
		result.Status, result.Error = "cancelled", "固定数量更新已取消"
	}
	return result
}

func finalizeFixedUpdate(scenario Scenario, archive *lifecycleArchive, result RunResult) RunResult {
	e := result.FixedUpdate
	if e == nil {
		return result
	}
	started, err := time.Parse(time.RFC3339Nano, e.StartedAt)
	if err != nil {
		result.Error = "更新测量起始时间无效"
		result.Status = "failed"
		return result
	}
	e.Completed = archive.Batch.Completed
	e.ElapsedMs = float64(time.Since(started)) / float64(time.Millisecond)
	e.Verified = archive.Batch.Error == "" && archive.Batch.CompletionRate != nil && archive.Batch.Eligible == fixedUpdateCount && archive.Batch.Excluded == 0
	if e.Verified {
		result.Summary.SuccessfulRequestsPerSec = float64(e.Completed) * 1000 / e.ElapsedMs
		result.Summary.SuccessRate = float64(e.Completed) * 100 / fixedUpdateCount
		result.PassedTPS = e.Submitted == fixedUpdateCount && compareThreshold(result.Summary.SuccessfulRequestsPerSec, scenario.TargetOperator, scenario.TargetTPS)
	}
	archive.Batch.SuccessfulTPS = result.Summary.SuccessfulRequestsPerSec
	archive.Batch.ElapsedMs = e.ElapsedMs
	archive.Batch.AcceptedTPS = e.AcceptedTPS
	return result
}
