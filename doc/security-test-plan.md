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

## Browser-Side Manual Steps (Generation Algorithm Tests)

### 1. 算法参数篡改攻击
模拟中间人篡改生成的公钥结构与参数。
1. 在Postman中准备一个正常的密钥生成或导入请求
2. 篡改请求体中的关键参数：
   - 原始公钥：`04abc123...` （130字符）
   - 篡改后：`04xyz789...` （130字符，但点不在曲线上）
3. 将公钥长度从130字符改为64字符，发送请求
4. 将公钥前缀从"04"改为"05"（无效的非压缩前缀），保持长度130字符不变，发送请求
5. 观察系统底层的算法框架是否能直接拦截该异常公钥并拒绝操作

### 2. 弱算法与参数降级攻击
模拟向生成算法层传入废弃的弱密码算法或极低的密钥位数。
1. 使用浏览器打开系统并登录（用户：testuser）
2. 抓取“密钥生成”表单提交的 `/keymanage/keymanage` POST请求
3. 导入到Postman并将请求体中的算法相关参数篡改：
   - 将请求的密钥长度篡改为低于安全阈值（例如将 RSA 2048 改为 512）
   - 将签名/加密哈希算法从安全的 SM3/SHA256 篡改为已废弃的 MD5
4. 点击"Send"发送请求
5. 验证后端底层密码机/算法库是否强制识别并拒绝生成此弱密钥，而非仅仅依赖前端界面的校验通过

### 3. 畸形密码格式载荷攻击
模拟向底层算法解析器发送破坏格式边界的边界请求。
1. 在Postman中准备一个包含十六进制、Base64或 ASN.1 格式的正常加载载荷
2. 破坏结构化数据边界：
   - 在密钥参数中注入非Hex字符（如 `04abXXzz...`）
   - 删除载荷的长度标记位或填充破坏格式对齐的数据
3. 点击"Send"发送构造的脏数据请求
4. 观察响应结果，验证算法库抛出安全的解析失败（如格式非法），且未因内存溢出导致不可控的服务错误或崩溃

## Expected Results

1. Algorithm Tampering: Tampered public key, invalid lengths, and unregistered prefixes must be directly rejected by the cryptographic library.
2. Weak Parameter: Lower-than-standard bit sizes or deprecated algorithms should fail to generate.
3. Malformed Validation: Bad ASN.1 or non-hex inputs should be cleanly intercepted via Type/Parse errors without affecting system stability.

## Follow-Up Enhancements

1. Add dedicated replay-id or nonce validation for critical generate and lifecycle mutations
2. Tighten `X-Frame-Options` or add CSP `frame-ancestors 'none'` if full anti-clickjacking is required
3. Add structured security regression script outputs for CI
