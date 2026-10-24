package main

import (
	"bytes"
	"context"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const generationCount = 6000

type generationSample struct {
	KeyID   int64  `json:"keyId"`
	Version int    `json:"version"`
	Status  string `json:"status"`
	Digest  string `json:"digest"`
}
type generationEvidence struct {
	Version      int                `json:"version"`
	Batch        string             `json:"batch"`
	Selected     int                `json:"selected"`
	Submitted    int                `json:"submitted"`
	HTTPSuccess  int                `json:"httpSuccess"`
	Accepted     int                `json:"accepted"`
	Registered   int                `json:"registered"`
	Completed    int                `json:"completed"`
	Duplicates   int                `json:"duplicates"`
	Invalid      int                `json:"invalid"`
	Failed       int                `json:"failed"`
	Verified     bool               `json:"verified"`
	StartedAt    string             `json:"startedAt"`
	ObservedAt   string             `json:"observedAt"`
	SubmissionMs float64            `json:"submissionMs"`
	ElapsedMs    float64            `json:"elapsedMs"`
	AcceptedTPS  float64            `json:"acceptedTps"`
	Samples      []generationSample `json:"samples"`
}

// Public SM2 points are prepared outside the measurement. Each input occurs
// once in a batch; starting from a random point also isolates separate runs.
func generationInputs(count int) ([]string, error) {
	hexInt := func(s string) *big.Int { n, _ := new(big.Int).SetString(s, 16); return n }
	c := &elliptic.CurveParams{Name: "SM2", BitSize: 256}
	c.P = hexInt("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF")
	c.N = hexInt("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123")
	c.B = hexInt("28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93")
	c.Gx = hexInt("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7")
	c.Gy = hexInt("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0")
	scalar, err := rand.Int(rand.Reader, new(big.Int).Sub(c.N, big.NewInt(int64(count+1))))
	if err != nil {
		return nil, err
	}
	scalar.Add(scalar, big.NewInt(1))
	x, y := c.ScalarBaseMult(scalar.Bytes())
	result := make([]string, count)
	for i := range result {
		result[i] = fmt.Sprintf("04%064x%064x", x, y)
		x, y = c.Add(x, y, c.Gx, c.Gy)
	}
	return result, nil
}

func (s *server) generationRecords(ctx context.Context, batch string) ([]internalKeyRecord, error) {
	endpoint, err := url.Parse(s.cfg.GenerateKeyPoolURL)
	if err != nil {
		return nil, err
	}
	q := endpoint.Query()
	q.Set("userName", s.cfg.AcceptanceUser)
	q.Set("keyName", batch)
	q.Set("encrytName", "SSCL")
	q.Set("limit", strconv.Itoa(generationCount+1))
	endpoint.RawQuery = q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Internal-Token", s.cfg.GenerateInternalToken)
	response, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("登记查询返回HTTP %d", response.StatusCode)
	}
	var payload internalGenerateResponse
	err = json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&payload)
	return payload.Data, err
}

// Count a key only when its ID, input and returned material all agree with the
// persisted record. Repeated IDs, inputs or material never increase completion.
func verifyGeneration(e *generationEvidence, rows []internalKeyRecord, states map[int64]internalVerifyRecord, expected map[string]string, user string) {
	e.Registered = len(rows)
	e.Completed = 0
	e.Duplicates = 0
	e.Invalid = 0
	e.Samples = nil
	ids := map[int64]bool{}
	uas := map[string]bool{}
	digests := map[string]bool{}
	for _, r := range rows {
		digest, ok := expected[r.UA]
		st, exists := states[r.KeyID]
		if !ok || digest == "" || !exists || !st.Exists || r.KeyID <= 0 || r.UserName != user || r.KeyDomain != "acceptance" || r.KeyName != e.Batch || r.EncrytName != "SSCL" || r.Status != "0" || st.UserName != user || st.KeyDomain != "acceptance" || st.Status != "0" || st.Version == nil || *st.Version < 1 || !strings.EqualFold(st.MaterialDigest, digest) {
			e.Invalid++
			continue
		}
		if ids[r.KeyID] || uas[r.UA] || digests[digest] {
			e.Duplicates++
			continue
		}
		ids[r.KeyID] = true
		uas[r.UA] = true
		digests[digest] = true
		e.Completed++
		if len(e.Samples) < 20 {
			e.Samples = append(e.Samples, generationSample{r.KeyID, *st.Version, st.Status, digest[:16]})
		}
	}
	e.Failed = max(0, e.Selected-e.Completed)
}

func (s *server) executeGeneration(parent context.Context, scenario Scenario) RunResult {
	ctx, cancel := context.WithTimeout(parent, 75*time.Second)
	defer cancel()
	inputs, err := generationInputs(generationCount)
	if err != nil {
		return RunResult{Status: "failed", Error: "无法准备独立生成输入"}
	}
	e := &generationEvidence{Version: 1, Batch: "acceptance-gen-" + s.nextID(), Selected: len(inputs)}
	// Prepare request bodies before starting the clock.
	bodies := make([][]byte, len(inputs))
	for i, ua := range inputs {
		bodies[i], _ = json.Marshal(map[string]string{"encryt_type": "无证书非对称加密", "encryt_name": "SSCL", "ua": ua, "key_domain": "acceptance", "key_name": e.Batch, "key_use": "性能验收", "auto_update": "false"})
	}
	workers := max(1, min(scenario.Connections, 100))
	client := *s.client
	if client.Transport == nil {
		tr := http.DefaultTransport.(*http.Transport).Clone()
		tr.MaxIdleConnsPerHost = workers
		tr.MaxConnsPerHost = workers
		client.Transport = tr
		defer tr.CloseIdleConnections()
	}
	expected := map[string]string{}
	var mu sync.Mutex
	var next atomic.Int64
	var wg sync.WaitGroup
	started := time.Now()
	e.StartedAt = started.Format(time.RFC3339Nano)
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				i := int(next.Add(1) - 1)
				if i >= len(inputs) || ctx.Err() != nil {
					return
				}
				req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(scenario.BaseURL, "/")+scenario.Path, bytes.NewReader(bodies[i]))
				if err != nil {
					continue
				}
				for k, v := range scenario.Headers {
					req.Header.Set(k, v)
				}
				req.Header.Set("Content-Type", "application/json")
				mu.Lock()
				e.Submitted++
				mu.Unlock()
				resp, err := client.Do(req)
				if err != nil {
					continue
				}
				var payload struct {
					Code int    `json:"code"`
					Data string `json:"data"`
				}
				decodeErr := json.NewDecoder(io.LimitReader(resp.Body, 64<<10)).Decode(&payload)
				resp.Body.Close()
				mu.Lock()
				if resp.StatusCode >= 200 && resp.StatusCode < 300 {
					e.HTTPSuccess++
				}
				if resp.StatusCode == 200 && decodeErr == nil && payload.Code == 200 && payload.Data != "" {
					sum := sha256.Sum256([]byte(payload.Data))
					expected[inputs[i]] = fmt.Sprintf("%x", sum)
					e.Accepted++
				}
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	e.SubmissionMs = float64(time.Since(started)) / float64(time.Millisecond)
	e.AcceptedTPS = float64(e.Accepted) * 1000 / e.SubmissionMs
	result := RunResult{Status: "failed_threshold", Generation: e}
	deadline := time.Now().Add(time.Duration(max(1, s.cfg.VerifyWaitSeconds)) * time.Second)
	var rows []internalKeyRecord
	for {
		rows, err = s.generationRecords(ctx, e.Batch)
		if err != nil {
			break
		}
		if len(rows) >= e.Accepted || time.Now().After(deadline) {
			break
		}
		select {
		case <-ctx.Done():
			err = ctx.Err()
		case <-time.After(200 * time.Millisecond):
		}
		if err != nil {
			break
		}
	}
	if err == nil {
		ids := make([]int64, 0, len(rows))
		seen := map[int64]bool{}
		for _, r := range rows {
			if r.KeyID > 0 && !seen[r.KeyID] {
				ids = append(ids, r.KeyID)
				seen[r.KeyID] = true
			}
		}
		var states map[int64]internalVerifyRecord
		states, err = s.captureLifecycle(ctx, ids)
		if err == nil {
			verifyGeneration(e, rows, states, expected, s.cfg.AcceptanceUser)
			e.Verified = true
		}
	}
	e.ElapsedMs = float64(time.Since(started)) / float64(time.Millisecond)
	e.ObservedAt = time.Now().Format(time.RFC3339Nano)
	result.Summary = RunSummary{TotalRequests: int64(e.Submitted), Non2xxResponses: int64(e.Submitted - e.HTTPSuccess), RequestsPerSec: float64(e.Submitted) * 1000 / e.SubmissionMs}
	if e.Verified {
		result.Summary.SuccessfulRequestsPerSec = float64(e.Completed) * 1000 / e.ElapsedMs
		result.Summary.SuccessRate = float64(e.Completed) * 100 / float64(e.Selected)
	}
	result.PassedTPS = e.Verified && e.Completed == e.Selected && e.Duplicates == 0 && e.Invalid == 0 && compareThreshold(result.Summary.SuccessfulRequestsPerSec, scenario.TargetOperator, scenario.TargetTPS)
	if result.PassedTPS {
		result.Status = "passed"
	}
	if err != nil {
		result.Status = "failed"
		result.Error = "真实生成登记核验未完成"
		e.Failed = e.Selected - e.Completed
	}
	if parent.Err() != nil {
		result.Status = "cancelled"
	}
	result.Notes = []string{"每轮6000个不同的有效SM2用户公钥输入，实际执行SSCL部分密钥生成。", "按独立标识、独立输入和材料摘要共同去重；材料明文不进入验收记录。", "计时从首次生成请求前至数据库登记、状态和材料摘要核验完成；不等待异步上链。"}
	return result
}
