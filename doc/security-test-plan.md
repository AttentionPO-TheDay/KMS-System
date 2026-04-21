# Security Test Plan

## Scope

1. Generate system attacks
2. Update and revoke system attacks
3. Login and traffic protection verification
4. Browser embedding and clickjacking verification

## Current Baseline

1. Generate and updatedel Java backends already enable `SmartSecurityFilter`
2. Login retry lock is configured as `maxRetryCount=5` and `lockTime=10`
3. `X-Frame-Options` is currently `SAMEORIGIN`, not full deny
4. Updatedel and generate now both support internal token forwarding to Go backends

## Automated Checks

Use `security/security_test.ps1` with explicit environment values.

1. Scanner User-Agent probe
2. Login brute-force simulation
3. Clickjacking header check
4. Internal interface smoke check

## Semi-Automated Business Attacks

### Crypto Algorithm Core (Generate)

1. Tamper attack on public key, length, and prefix (Invalid Curve/Formats)
2. Weak parameter attack (Downgrade to weak keys or curves)
3. Malformed payload attack (Corrupted structures causing parser errors)

### API & Interface Security

1. SQL injection payloads against query and form parameters
2. XSS payload submission and replay
3. Replay attack using captured API requests (Generate/Update)
4. Privilege escalation with normal user token (Horizontal/Vertical)

### Update and Revoke

1. SQL injection payloads against key query and record query inputs
2. XSS payload submission on editable key metadata
3. Replay attack on update and revoke requests
4. Tamper attack on `keyId`, `user`, and body fields
5. Privilege escalation by operating on foreign keys

## Browser-Side Manual Steps

### 1. 模拟重放攻击请求
1. 使用浏览器打开系统并登录（用户：testuser）
2. 打开浏览器开发者工具（F12）→ Network标签
3. 进入"用户密钥"页面，点击"密钥生成"
4. 填写密钥生成表单：
   - 加密算法类型：无证书非对称加密
   - 加密算法名称：SM2
   - 密钥名称：测试密钥001
   - 密钥用途：数据加密
5. 点击"确定"提交
6. 在Network中找到 `/keymanage/keymanage` 的POST请求
7. 右键 → Copy → Copy as cURL
8. 等待5秒后，在Postman中粘贴刚才复制的cURL命令
9. 导入到Postman（Import → Raw text → Continue）
10. 点击"Send"发送请求观察响应结果

### 2. 模拟中间人篡改请求
1. 在Postman中准备一个正常的密钥生成请求
2. 篡改请求体中的关键参数：
   - 原始公钥：`04abc123...` （130字符）
   - 篡改后：`04xyz789...` （130字符，但点不在曲线上）
3. 将公钥长度从130字符改为64字符，发送请求
4. 将公钥前缀从"04"改为"05"，保持长度130字符不变，发送请求
5. 观察系统是否能在算法层或协议层直接拦截非法公钥

### 3. 模拟越权操作攻击
1. 分别登录以下用户，获取JWT Token（普通用户与无此权限用户）
2. 在Postman中保存这两个 Token 环境变量
3. 使用普通用户Token发送查看所有公共密钥请求或管理员级别请求
4. 观察系统是否返回 403 或拦截提示

## Expected Results

1. Scanner UA should be blocked with `403`
2. Sixth login attempt after five failures should still be blocked during lock window
3. Replay requests should not create repeated effective business results
4. Tampered public key and malformed body should be directly rejected by crypto library/parser
5. Normal user tokens should not access admin-only or foreign-user resources
6. Clickjacking validation should currently show `SAMEORIGIN`; if the requirement becomes strict anti-framing, backend headers must be tightened later

## Follow-Up Enhancements

1. Add dedicated replay-id or nonce validation for critical generate and lifecycle mutations
2. Tighten `X-Frame-Options` or add CSP `frame-ancestors 'none'` if full anti-clickjacking is required
3. Add structured security regression script outputs for CI
