package main

// Fixed, non-destructive probes for the current passwordless Demo protocol.
// No public key is registered, rotated or revoked; only an isolated session is changed.
import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"strconv"
	"strings"
	"time"
)

var systemSecurityCases = map[string]bool{
	"generation-identity-injection": true, "generation-unknown-algorithm": true, "generation-malformed-json": true,
	"pq-parameter-downgrade": true, "pq-sign-encrypt-confusion": true, "pq-secret-upload": true,
	"network-session-forgery": true, "network-csrf": true, "network-stale-revision": true,
	"network-role-isolation": true, "network-origin": true,
}

type securityProbe struct {
	client   *http.Client
	base     string
	csrf     string
	revision int
	node     string
	result   SecurityRunResult
}

func (p *securityProbe) request(ctx context.Context, method, path, body string, overrides map[string]string) (int, map[string]interface{}, error) {
	req, err := http.NewRequestWithContext(ctx, method, p.base+path, strings.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	req.Host = "127.0.0.1:8088"
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Origin", "http://127.0.0.1:8088")
	if p.csrf != "" {
		req.Header.Set("X-Kms-Demo-CSRF", p.csrf)
		req.Header.Set("X-Kms-Demo-Revision", strconv.Itoa(p.revision))
	}
	for k, v := range overrides {
		req.Header.Set(k, v)
	}
	client := p.client
	if _, forged := overrides["Cookie"]; forged {
		copyClient := *client
		copyClient.Jar = nil
		client = &copyClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		return resp.StatusCode, nil, err
	}
	var data map[string]interface{}
	if err := json.Unmarshal(raw, &data); err != nil {
		return resp.StatusCode, nil, fmt.Errorf("目标未返回 JSON (HTTP %d)", resp.StatusCode)
	}
	// Deliberately do not record body/cookies/public keys/authorization material.
	code := probeErrorCode(data)
	p.result.Requests = append(p.result.Requests, SecurityRequestTrace{Name: path, Method: method, URL: path, StatusCode: resp.StatusCode, Message: fmt.Sprintf("businessCode=%v errorCode=%s", data["code"], code)})
	return resp.StatusCode, data, nil
}

func probeErrorCode(data map[string]interface{}) string {
	if nested, ok := data["data"].(map[string]interface{}); ok {
		if code, ok := nested["error_code"].(string); ok {
			return code
		}
	}
	for _, name := range []string{"errorCode", "error_code", "message", "msg"} {
		if code, ok := data[name].(string); ok {
			return code
		}
	}
	return ""
}

func (p *securityProbe) control(ctx context.Context) (map[string]interface{}, error) {
	status, data, err := p.request(ctx, "GET", "/demo-api/pqkds/node-self/", "", nil)
	if err != nil {
		return nil, err
	}
	if status != 200 || data["code"] != float64(200) {
		return nil, fmt.Errorf("合法节点读取不可用，不能计为防御成功 (HTTP %d)", status)
	}
	d, ok := data["data"].(map[string]interface{})
	if !ok || d["mapped"] != true {
		return nil, fmt.Errorf("合法对照未关联节点")
	}
	node, ok := d["node"].(map[string]interface{})
	if !ok || node["nodeId"] != p.node {
		return nil, fmt.Errorf("合法对照节点身份已改变")
	}
	return data, nil
}

func (s *server) executeSystemSecurity(ctx context.Context, caseID string) SecurityRunResult {
	jar, _ := cookiejar.New(nil)
	p := securityProbe{base: strings.TrimRight(envOrDefault("ACCEPTANCE_SECURITY_GATEWAY_URL", "http://kms_gateway:8088"), "/"),
		client: &http.Client{Jar: jar, Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }},
		result: SecurityRunResult{CaseID: caseID, Status: "error", Verdict: "error", Notes: []string{"固定协议探针；只创建临时演示会话，不登记、更新或回收业务密钥。", "不证明抗量子计算能力，不覆盖节点侧私钥/密文密码学测试。"}}}
	fail := func(err error) SecurityRunResult {
		p.result.Error = err.Error()
		p.result.Summary = "前置条件或响应证据不足，未计为防御成功"
		return p.result
	}
	status, initial, err := p.request(ctx, "GET", "/demo-api/lifecycle/demo/context", "", nil)
	if err != nil {
		return fail(err)
	}
	d, ok := initial["data"].(map[string]interface{})
	if status != 200 || initial["code"] != float64(200) || !ok || d["enabled"] != true {
		return fail(fmt.Errorf("受控网关未就绪"))
	}
	p.csrf, _ = d["csrfToken"].(string)
	node := envOrDefault("ACCEPTANCE_SECURITY_NODE_ID", "demo-0")
	p.node = node
	body, _ := json.Marshal(map[string]string{"nodeId": node})
	status, entered, err := p.request(ctx, "POST", "/demo-api/lifecycle/demo/context/entry", string(body), nil)
	if err != nil {
		return fail(err)
	}
	d, ok = entered["data"].(map[string]interface{})
	if status != 200 || entered["code"] != float64(200) || !ok || d["principalType"] != "NODE" {
		return fail(fmt.Errorf("测试节点 %s 无法进入；不会自动创建节点", node))
	}
	p.csrf, _ = d["csrfToken"].(string)
	revision, ok := d["revision"].(float64)
	if p.csrf == "" || !ok {
		return fail(fmt.Errorf("临时会话缺少可信版本/CSRF"))
	}
	p.revision = int(revision)
	defer func() {
		cleanup, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_, _, _ = p.request(cleanup, "POST", "/demo-api/lifecycle/demo/context/logout", "{}", nil)
	}()
	if _, err = p.control(ctx); err != nil {
		return fail(err)
	}
	method, path, payload := "POST", "/demo-api/pqkds/node-self/keygen/issuances/", ""
	headers := map[string]string{}
	expected, explanation := "INVALID_PARAMETER", "请求应在生成发放前被拒绝"
	if strings.HasPrefix(caseID, "network-") {
		explanation = "非法会话或权限请求已被拒绝，原节点身份保持不变"
	}
	switch caseID {
	case "generation-identity-injection":
		payload = `{"algorithm":"KYBER","nodeId":"foreign-node"}`
	case "generation-unknown-algorithm":
		payload = `{"algorithm":"RSA-512","keyId":"acceptance-invalid","keyVersion":1,"variant":"512"}`
		expected = "KEYGEN_SCHEME_INVALID"
	case "generation-malformed-json":
		payload = `{"algorithm":`
	case "pq-parameter-downgrade":
		payload = `{"algorithm":"KYBER","keyId":"acceptance-invalid","keyVersion":1,"variant":"128"}`
	case "pq-sign-encrypt-confusion":
		payload = `{"algorithm":"FALCON","keyId":"acceptance-invalid","keyVersion":1,"variant":"768"}`
		explanation = "标准签名家族不能使用封装家族的参数集；仅验证签发参数边界"
	case "pq-secret-upload":
		payload = `{"algorithm":"KYBER","secretKey":"acceptance-dummy-not-a-key"}`
	case "network-session-forgery":
		method, path = "GET", "/demo-api/pqkds/node-self/"
		headers["Cookie"] = "KMS-Demo-Session=" + strings.Repeat("A", 43)
		expected = "DEMO_CONTEXT_STALE"
	case "network-csrf":
		path, payload = "/demo-api/lifecycle/demo/context/admin", "{}"
		headers["X-Kms-Demo-CSRF"] = "acceptance-invalid"
		expected = "DEMO_CSRF_INVALID"
	case "network-stale-revision":
		path, payload = "/demo-api/lifecycle/demo/context/admin", "{}"
		headers["X-Kms-Demo-Revision"] = strconv.Itoa(p.revision - 1)
		expected = "DEMO_REVISION_STALE"
	case "network-role-isolation":
		method, path = "GET", "/demo-api/pqkds/admin/users/"
		expected = "DEMO_FORBIDDEN"
	case "network-origin":
		path, payload = "/demo-api/lifecycle/demo/context/admin", "{}"
		headers["Origin"] = "https://acceptance-invalid.example"
		expected = "DEMO_ORIGIN_REJECTED"
	default:
		return fail(fmt.Errorf("未知当前系统用例"))
	}
	status, response, err := p.request(ctx, method, path, payload, headers)
	if err != nil {
		return fail(err)
	}
	actual := probeErrorCode(response)
	if status == 404 || status >= 500 {
		return fail(fmt.Errorf("目标不存在或服务异常 (HTTP %d)", status))
	}
	if _, err = p.control(ctx); err != nil {
		return fail(err)
	}
	p.result.Status = "completed"
	businessCode, _ := response["code"].(float64)
	rejected := (status >= 400 && status < 500) || (status == 200 && businessCode >= 400 && businessCode < 500)
	p.result.Passed = rejected && actual == expected
	if p.result.Passed {
		p.result.Verdict = "blocked"
		p.result.Summary = explanation + "；已获得明确拒绝码 " + expected + "，合法节点读取仍正常"
	} else {
		p.result.Verdict = "vulnerable"
		p.result.Summary = fmt.Sprintf("未满足指定拒绝断言：HTTP %d，实际 %s，预期 %s；需复核", status, actual, expected)
	}
	return p.result
}
