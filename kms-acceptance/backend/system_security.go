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
	"quantum-lwe-usvp": true, "quantum-lwe-bdd": true, "quantum-lwe-dual": true,
	"generation-identity-injection": true, "generation-unknown-algorithm": true, "generation-malformed-json": true, "generation-invalid-version": true,
	"network-session-forgery": true, "network-csrf": true, "network-stale-revision": true,
	"network-role-isolation": true, "network-origin": true, "network-missing-session": true,
}

type securityProbe struct {
	client   *http.Client
	base     string
	csrf     string
	revision int
	node     string
	result   SecurityRunResult
}

type securityProgressKey struct{}

func (p *securityProbe) progress(ctx context.Context, stage string) {
	p.result.Stage = stage
	if report, ok := ctx.Value(securityProgressKey{}).(func(SecurityRunResult)); ok {
		snapshot := p.result
		snapshot.Requests = append([]SecurityRequestTrace(nil), p.result.Requests...)
		snapshot.ProbeSteps = append([]SecurityProbeStep(nil), p.result.ProbeSteps...)
		report(snapshot)
	}
}

func (p *securityProbe) request(ctx context.Context, method, path, body string, overrides map[string]string) (int, map[string]interface{}, error) {
	req, err := http.NewRequestWithContext(ctx, method, p.base+path, strings.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	started := time.Now()
	trace := SecurityRequestTrace{Name: p.result.Stage, Method: method, URL: path, Outcome: "error"}
	defer func() {
		trace.RecordedAt = time.Now().Format(time.RFC3339Nano)
		trace.DurationMs = time.Since(started).Milliseconds()
		p.result.Requests = append(p.result.Requests, trace)
		p.progress(ctx, p.result.Stage)
	}()
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
		p.recordStep(ctx, "TRANSPORT", "隔离本次请求的 Cookie 发送", "本次请求禁用 CookieJar，避免合法会话自动附加；原客户端保持不变", "info")
		p.progress(ctx, trace.Name)
	}
	resp, err := client.Do(req)
	if err != nil {
		trace.Message = "请求未获得有效响应: " + err.Error()
		return 0, nil, err
	}
	trace.StatusCode = resp.StatusCode
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		trace.Message = "读取响应失败: " + err.Error()
		return resp.StatusCode, nil, err
	}
	var data map[string]interface{}
	if err := json.Unmarshal(raw, &data); err != nil {
		trace.Message = "目标未返回 JSON"
		return resp.StatusCode, nil, fmt.Errorf("目标未返回 JSON (HTTP %d)", resp.StatusCode)
	}
	// Deliberately do not record body/cookies/public keys/authorization material.
	code := probeErrorCode(data)
	trace.Outcome = "received"
	trace.Message = fmt.Sprintf("businessCode=%v errorCode=%s", data["code"], code)
	if reason := probeRejectionReason(data); reason != "" {
		trace.Message += " reason=" + reason
	}
	return resp.StatusCode, data, nil
}

// Only literal, reviewed public rejection messages may enter persisted evidence.
// Never copy arbitrary response messages: they may contain echoed key material.
func probeRejectionReason(data map[string]interface{}) string {
	message, _ := data["msg"].(string)
	switch message {
	case "签发只接受白名单字段，可信上下文由后端确定", "签发仅支持规范 KYBER/FALCON 家族",
		"请求参数或 JSON 无效", "keyVersion 应为 ≥1 的整数：1.5", "生成参数集无效",
		"公钥接口禁止上传私密生成材料", "指定的放弃来源不存在", "DEMO_SESSION_INVALID",
		"缺少 Demo 会话", "DEMO_CSRF_INVALID", "DEMO_REVISION_STALE", "演示节点不能访问管理接口", "DEMO_ORIGIN_REJECTED":
		return message
	}
	return ""
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

func (p *securityProbe) control(ctx context.Context) (result map[string]interface{}, controlErr error) {
	name := "攻击后合法节点读取"
	if strings.Contains(p.result.Stage, "攻击前") {
		name = "攻击前合法节点读取"
	}
	status, data, err := p.request(ctx, "GET", "/demo-api/pqkds/node-self/", "", nil)
	defer func() {
		d, _ := data["data"].(map[string]interface{})
		node, _ := d["node"].(map[string]interface{})
		actualNode, _ := node["nodeId"].(string)
		state := "failed"
		if controlErr == nil {
			state = "success"
		}
		p.recordStep(ctx, "CONTROL", name,
			fmt.Sprintf("GET /demo-api/pqkds/node-self/; HTTP=%d; businessCode=%v; expectedNodeId=%s; actualNodeId=%s; mapped=%t; identityMatched=%t",
				status, data["code"], p.node, actualNode, d["mapped"] == true, actualNode != "" && actualNode == p.node), state)
	}()
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
		result: SecurityRunResult{CaseID: caseID, Status: "error", Verdict: "error", Notes: []string{"固定协议探针；只创建临时演示会话，不登记、更新或回收业务密钥。"}}}
	p.result.EvidenceVersion = 2
	fail := func(err error) SecurityRunResult {
		p.result.Error = err.Error()
		p.result.Summary = "前置条件或响应证据不足，未计为防御成功"
		return p.result
	}
	p.progress(ctx, "建立独立测试会话")
	status, initial, err := p.request(ctx, "GET", "/demo-api/lifecycle/demo/context", "", nil)
	if err != nil {
		return fail(err)
	}
	d, ok := initial["data"].(map[string]interface{})
	if status != 200 || initial["code"] != float64(200) || !ok || d["enabled"] != true {
		return fail(fmt.Errorf("受控网关未就绪"))
	}
	p.csrf, _ = d["csrfToken"].(string)
	node := envOrDefault("ACCEPTANCE_SECURITY_NODE_ID", "A")
	p.node = node
	body, _ := json.Marshal(map[string]string{"nodeId": node})
	p.progress(ctx, "进入测试节点 "+node)
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
	p.progress(ctx, "攻击前验证合法节点读取")
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
		expected = "KEYGEN_IDENTITY_FIELD_FORBIDDEN"
		input := map[string]interface{}{"algorithm": "KYBER", "keyId": "acceptance-invalid", "keyVersion": 1, "variant": "768"}
		p.recordStep(ctx, "BUILD", "构造正常格式的 KYBER 签发参数", "algorithm=KYBER; variant=768; keyVersion=1", "info")
		input["nodeId"] = "foreign-node"
		p.recordStep(ctx, "MUTATE", "注入外部节点身份", "新增 nodeId=foreign-node，尝试覆盖服务端可信身份", "info")
		encoded, _ := json.Marshal(input)
		payload = string(encoded)
		p.recordStep(ctx, "BUILD", "序列化身份注入请求", fmt.Sprintf("JSON 编码完成，%d 字节；包含额外身份字段", len(encoded)), "info")
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "KYBER / variant=768；额外注入 nodeId=foreign-node", "签发字段白名单，身份由会话决定", "签发只接受白名单字段，可信上下文由后端确定"
	case "generation-unknown-algorithm":
		payload = `{"algorithm":"RSA-512","keyId":"acceptance-invalid","keyVersion":1,"variant":"512"}`
		p.recordStep(ctx, "BUILD", "构造非白名单算法请求", "algorithm=RSA-512; variant=512; keyVersion=1", "info")
		expected = "KEYGEN_SCHEME_INVALID"
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "algorithm=RSA-512", "生成算法白名单", "签发仅支持规范 KYBER/FALCON 家族"
	case "generation-malformed-json":
		expected = "KEYGEN_JSON_INVALID"
		payload = `{"algorithm":`
		p.recordStep(ctx, "BUILD", "构造残缺 JSON 字节串", "保留 algorithm 字段前缀，省略字段值和闭合括号", "info")
		p.recordStep(ctx, "CHECK", "检查畸形样本语法", fmt.Sprintf("json.Valid=%t；不经 JSON 序列化修复，按原始字节发送", json.Valid([]byte(payload))), "info")
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "残缺 JSON：缺少 algorithm 的值及闭合括号", "JSON 请求解析", "请求参数或 JSON 无效"
	case "generation-invalid-version":
		expected = "KEYGEN_VERSION_INVALID"
		payload = `{"algorithm":"KYBER","keyId":"acceptance-invalid-version","keyVersion":1.5,"variant":"768"}`
		p.recordStep(ctx, "BUILD", "构造小数版本号请求", "keyVersion=1.5，以 JSON 数值发送，不转换为整数或字符串", "info")
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "KYBER / variant=768 / keyVersion=1.5", "密钥版本正整数约束", "keyVersion 应为 ≥1 的整数：1.5"
	case "pq-parameter-downgrade":
		expected = "KYBER_KEYGEN_VARIANT_INVALID"
		payload = `{"algorithm":"KYBER","keyId":"acceptance-invalid","keyVersion":1,"variant":"128"}`
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "KYBER / variant=128；支持值为 512、768、1024", "算法与参数集白名单", "生成参数集无效"
	case "pq-sign-encrypt-confusion":
		expected = "FALCON_KEYGEN_VARIANT_INVALID"
		payload = `{"algorithm":"FALCON","keyId":"acceptance-invalid","keyVersion":1,"variant":"768"}`
		explanation = "标准签名家族不能使用封装家族的参数集；仅验证签发参数边界"
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "FALCON / variant=768；该签名家族仅支持 512", "算法与参数集白名单", "生成参数集无效"
	case "pq-secret-upload":
		expected = "KEYGEN_PRIVATE_MATERIAL_FORBIDDEN"
		payload = `{"algorithm":"KYBER","keyId":"acceptance-invalid","keyVersion":1,"variant":"768","secretKey":"acceptance-dummy-not-a-key"}`
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "KYBER / variant=768；附加虚构 secretKey 字段", "私密生成材料禁入", "公钥接口禁止上传私密生成材料"
	case "pq-issuance-source-forgery":
		payload = `{"algorithm":"KYBER","keyId":"acceptance-invalid-source","keyVersion":1,"variant":"768","abandonGenerationIssuanceId":"acceptance-not-an-issuance"}`
		expected = "KEYGEN_ISSUANCE_CONFLICT"
		explanation = "伪造的来源替换引用已被拒绝，未创建或替换签发来源"
		p.result.TestInput, p.result.ValidationRule, p.result.ExpectedReason = "abandonGenerationIssuanceId=acceptance-not-an-issuance", "签发来源存在性约束", "指定的放弃来源不存在"
	case "network-session-forgery":
		method, path = "GET", "/demo-api/pqkds/node-self/"
		headers["Cookie"] = "KMS-Demo-Session=" + strings.Repeat("A", 43)
		p.recordStep(ctx, "MUTATE", "构造伪造会话 Cookie", "KMS-Demo-Session 使用固定虚构值，长度 43；不使用真实会话凭据", "info")
		expected = "DEMO_SESSION_INVALID"
	case "network-missing-session":
		method, path = "GET", "/demo-api/pqkds/node-self/"
		headers["Cookie"] = ""
		p.recordStep(ctx, "MUTATE", "移除请求会话", "Cookie 设为空，测试匿名读取节点资料", "info")
		expected = "DEMO_SESSION_REQUIRED"
	case "network-csrf":
		path, payload = "/demo-api/lifecycle/demo/context/admin", "{}"
		headers["X-Kms-Demo-CSRF"] = "acceptance-invalid"
		p.recordStep(ctx, "MUTATE", "替换 CSRF 请求头", "X-Kms-Demo-CSRF 使用固定错误值；保留当前会话与 revision", "info")
		expected = "DEMO_CSRF_INVALID"
	case "network-stale-revision":
		path, payload = "/demo-api/lifecycle/demo/context/admin", "{}"
		stale := p.revision - 1
		p.recordStep(ctx, "BUILD", "计算旧会话版本", fmt.Sprintf("当前 revision=%d；重放版本=%d", p.revision, stale), "info")
		headers["X-Kms-Demo-Revision"] = strconv.Itoa(stale)
		p.recordStep(ctx, "MUTATE", "替换版本请求头", "X-Kms-Demo-Revision 写入上一版本；保留合法会话和 CSRF", "info")
		expected = "DEMO_REVISION_STALE"
	case "network-role-isolation":
		method, path = "GET", "/demo-api/pqkds/admin/users/"
		p.recordStep(ctx, "BUILD", "选择管理员资源作为访问目标", "GET /demo-api/pqkds/admin/users/；使用现有 NODE 身份，不执行管理员角色切换", "info")
		expected = "DEMO_FORBIDDEN"
	case "network-origin":
		path, payload = "/demo-api/lifecycle/demo/context/admin", "{}"
		headers["Origin"] = "https://acceptance-invalid.example"
		p.recordStep(ctx, "MUTATE", "替换请求来源", "Origin=https://acceptance-invalid.example；保留原会话、CSRF 和 revision", "info")
		expected = "DEMO_ORIGIN_REJECTED"
	default:
		return fail(fmt.Errorf("未知当前系统用例"))
	}
	p.result.ExpectedCode = expected
	if strings.HasPrefix(caseID, "network-") {
		p.result.TestInput = map[string]string{
			"network-session-forgery": "伪造 Cookie 读取节点资料", "network-missing-session": "不带 Cookie 读取节点资料",
			"network-csrf": "错误 CSRF 请求角色切换", "network-stale-revision": "上一 revision 请求角色切换",
			"network-role-isolation": "节点会话读取管理员接口", "network-origin": "不受信任 Origin 请求角色切换",
		}[caseID]
		p.result.ValidationRule = map[string]string{
			"network-session-forgery": "已提供会话的有效性校验", "network-missing-session": "会话存在性校验",
			"network-csrf": "CSRF 凭据一致性校验", "network-stale-revision": "会话 revision 栅栏",
			"network-role-isolation": "节点与管理员权限隔离", "network-origin": "请求来源白名单",
		}[caseID]
		p.result.ExpectedReason = map[string]string{
			"network-session-forgery": "DEMO_SESSION_INVALID", "network-missing-session": "缺少 Demo 会话",
			"network-csrf": "DEMO_CSRF_INVALID", "network-stale-revision": "DEMO_REVISION_STALE",
			"network-role-isolation": "演示节点不能访问管理接口", "network-origin": "DEMO_ORIGIN_REJECTED",
		}[caseID]
	}
	p.progress(ctx, "发送非法请求并核对拒绝原因")
	status, response, err := p.request(ctx, method, path, payload, headers)
	if err != nil {
		return fail(err)
	}
	actual := probeErrorCode(response)
	p.result.ActualCode = actual
	p.result.ActualReason = probeRejectionReason(response)
	p.result.ReasonMatched = p.result.ActualReason != "" && p.result.ActualReason == p.result.ExpectedReason
	businessCode, _ := response["code"].(float64)
	rejected := (status >= 400 && status < 500) || (status == 200 && businessCode >= 400 && businessCode < 500)
	assertionState := "failed"
	if rejected && actual == expected && p.result.ReasonMatched {
		assertionState = "success"
	}
	p.recordStep(ctx, "ASSERT", "核对本项防御断言", fmt.Sprintf("HTTP=%d; actualCode=%s; expectedCode=%s; reasonMatched=%t", status, actual, expected, p.result.ReasonMatched), assertionState)
	if status == 404 || status >= 500 {
		return fail(fmt.Errorf("目标不存在或服务异常 (HTTP %d)", status))
	}
	p.progress(ctx, "攻击后复查合法节点读取")
	if _, err = p.control(ctx); err != nil {
		return fail(err)
	}
	p.result.LegalControlPassed = true
	p.result.Status = "completed"
	p.result.Passed = rejected && actual == expected && p.result.ReasonMatched
	p.result.ProtocolPassed = p.result.Passed
	if p.result.Passed {
		p.result.Verdict = "blocked"
		p.result.Summary = explanation + "；拒绝原因已匹配：" + p.result.ActualReason + "；合法节点读取仍正常"
	} else {
		p.result.Verdict = "vulnerable"
		if rejected && actual == expected {
			p.result.Verdict = "insufficient_evidence"
		}
		p.result.Summary = fmt.Sprintf("未满足目标规则断言：HTTP %d，实际码 %s，预期码 %s；拒绝原因匹配=%t。原因缺失或不同不能证明命中本项规则。", status, actual, expected, p.result.ReasonMatched)
	}
	if strings.HasPrefix(caseID, "pq-") {
		p.result.EvidenceVersion = 3
		p.result.Notes = append(p.result.Notes, "算法验证仅使用本次生成的临时材料与公开测试向量，不读取浏览器或业务私钥；结果对应部署原生算法库，不代表自定义无证书方案的安全证明、FIPS认证或量子攻击实测。")
		p.progress(ctx, "执行真实算法正常对照、独立实现互操作及篡改/错钥验证")
		status, data, err := p.request(ctx, "POST", "/demo-api/pqkds/node-self/acceptance/pq/", `{"caseId":"`+caseID+`"}`, nil)
		if err != nil || status != 200 || data["code"] != float64(200) {
			p.result.Passed = false
			p.result.Status, p.result.Verdict = "error", "insufficient_evidence"
			p.result.Error = "算法验证未取得有效响应，不能计为通过"
			return p.result
		}
		raw, _ := json.Marshal(data["data"])
		var evidence AlgorithmEvidence
		if json.Unmarshal(raw, &evidence) != nil || !validAlgorithmEvidence(caseID, &evidence) {
			p.result.Passed = false
			p.result.Status, p.result.Verdict = "error", "insufficient_evidence"
			p.result.Error = "算法证据缺项或格式不符，不能计为通过"
			return p.result
		}
		p.result.AlgorithmEvidence = &evidence
		p.result.Passed = p.result.ProtocolPassed && evidence.Passed
		p.result.Summary = fmt.Sprintf("协议校验通过=%t；算法检查 %d/%d 通过；逐项过程、预期与实际结果见下方。", p.result.ProtocolPassed, passedAlgorithmChecks(evidence.Checks), len(evidence.Checks))
		p.result.Verdict = "blocked"
		if !p.result.Passed {
			p.result.Verdict = "vulnerable"
		}
		for _, check := range evidence.Checks {
			if check.Status == "error" {
				p.result.Status, p.result.Verdict = "error", "insufficient_evidence"
				p.result.Passed = false
				p.result.Error = "算法检查执行异常，未取得完整证据"
			}
		}
		p.progress(ctx, "算法检查完成，复查合法节点读取")
		if _, err := p.control(ctx); err != nil {
			p.result.Passed, p.result.LegalControlPassed = false, false
			return fail(err)
		}
	}
	return p.result
}
