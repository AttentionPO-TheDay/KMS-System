export const securitySuites = [
  {
    id: 'crypto-algorithm',
    name: '密码核心算法 3 类攻击',
    accent: 'accent-red',
    summary: '针对密码生成算法及底层结构的受击面测试，验证系统对弱参数、非法曲线和畸形数据格式的拒绝能力。',
    cases: [
      {
        caseId: 'algo-tamper',
        title: '算法参数篡改',
        mode: '自动化',
        target: 'ENROLL_KEY 公钥 UA 参数校验（长度、前缀、曲线验证）',
        expected: '非法公钥点、非法长度或前缀（如05）应在协议层直接被拒绝。',
        steps: [
          '篡改公钥使其不在椭圆曲线上，发送 ENROLL_KEY 请求',
          '将公钥长度从 130 改为 64 字符重发',
          '将公钥前缀从 04 改为 05 重发'
        ]
      },
      {
        caseId: 'algo-weak-param',
        title: '弱算法降级攻击',
        mode: '自动化',
        target: '算法类型与名称强制校验（encryt_type / encryt_name）',
        expected: '后台密码模块应强制拒绝不安全参数，不再生成低强度密钥。',
        steps: [
          '将算法名称篡改为废弃的 RSA-512，发送生成请求',
          '将算法名称篡改为不安全的 MD5，发送生成请求',
          '将算法类型设为空字符串，发送生成请求'
        ]
      },
      {
        caseId: 'algo-malformed',
        title: '畸形密码载荷攻击',
        mode: '自动化',
        target: '解析器健壮性：破坏格式边界',
        expected: '算法解析器不应抛出内存溢出或拒绝服务，应安全拦截。',
        steps: [
          '在公钥参数中注入非十六进制字符（如 04abXXzz...）',
          '发送超长公钥字符串（2000 字符）突破解析边界',
          '发送完全非法的请求体（破坏 JSON 结构）'
        ]
      }
    ]
  },
  {
    id: 'lifecycle-attacks',
    name: '更新与回收 5 类攻击',
    accent: 'accent-orange',
    summary: '针对更新与回收系统的 5 类攻击：SQL 注入、XSS、扫描工具识别、登录暴力破解、点击劫持防护验证。',
    cases: [
      {
        caseId: 'lifecycle-sql',
        title: 'SQL 注入',
        mode: '半自动',
        target: '我的密钥、结果查询、操作记录查询条件',
        expected: '仅返回正常参数校验或空结果，不应出现异常 SQL 行为。',
        steps: [
          '对 keyName、actionType、record query 注入 SQL payload',
          '检查响应和列表结果是否异常'
        ]
      },
      {
        caseId: 'lifecycle-xss',
        title: 'XSS',
        mode: '半自动',
        target: '更新时可编辑的 keyName、keyUse、keyDomain',
        expected: '恶意脚本不应在我的密钥、详情、结果页执行。',
        steps: [
          '提交带 script/onload payload 的更新请求',
          '刷新列表和详情页确认仅文本显示'
        ]
      },
      {
        caseId: 'platform-scanner',
        title: '扫描工具识别',
        mode: '自动化',
        target: 'SmartSecurityFilter 恶意 User-Agent 检测与 IP 黑名单',
        expected: '恶意 User-Agent 访问应返回 403，后续访问进入黑名单窗口。',
        steps: [
          '使用 sqlmap User-Agent 发送请求，验证返回 403',
          '使用 nikto User-Agent 发送请求，验证返回 403',
          '使用正常 User-Agent 验证未被牵连',
          '安全模式：自动清除黑名单恢复系统'
        ]
      },
      {
        caseId: 'platform-bruteforce',
        title: '登录暴力破解',
        mode: '自动化',
        target: '登录限流与锁定机制（LoginAttemptService）',
        expected: '连续 5 次错误后，第 6 次仍处于锁定窗口，提示账号已锁定。',
        steps: [
          '使用错误密码连续登录 6 次',
          '验证第 5 次后触发锁定',
          '验证第 6 次返回锁定提示',
          '安全模式：自动清除锁定状态恢复系统'
        ]
      },
      {
        caseId: 'platform-clickjack',
        title: '点击劫持',
        mode: '自动化',
        target: '响应头 X-Frame-Options 与 CSP frame-ancestors',
        expected: '所有端点均具备 iframe 嵌套防护响应头。',
        steps: [
          '检查 Nginx 网关的 X-Frame-Options 响应头',
          '检查 Java 后端 API 的 X-Frame-Options 响应头',
          '验证所有端点返回 SAMEORIGIN 或 DENY'
        ]
      }
    ]
  }
]

export const securityAssets = [
  { name: '安全测试总方案', path: 'doc/security-test-plan.md', desc: '覆盖攻击范围、执行方式、预期结果与后续加固建议。' },
  { name: '自动化脚本入口', path: 'security/security_test.sh', desc: '包含算法攻击、SQL/XSS、扫描器探测、登录暴破、点击劫持等攻击脚本。' }
]

// ──────────────────────────────────────────────────────────────────────
// ARCHIVED: 以下攻击场景暂时封存，不在 UI 中展示。
// PS1 脚本中对应的实现也已注释封存，如需恢复可取消注释。
// ──────────────────────────────────────────────────────────────────────
//
// === 业务接口 2 类攻击 (api-security) ===
//
// {
//   id: 'api-security',
//   name: '业务接口 2 类攻击',
//   accent: 'accent-blue',
//   summary: '按通用 API 安全口径测试，包含对密钥操作请求的重放利用和越权数据访问。',
//   cases: [
//     {
//       caseId: 'api-replay',
//       title: '接口重放攻击',
//       mode: 'Postman 导入',
//       target: 'POST /keymanage/keymanage 生效鉴权',
//       expected: '再次发送被拦截或记录重复，不应导致额外成功或异常错误。',
//       steps: ['由于 cURL 复制了有效 Token，延迟后重放', '观察后端对旧请求和高频发送的重放防护']
//     },
//     {
//       caseId: 'api-privilege',
//       title: '业务越权访问',
//       mode: '多用户 Token 互试',
//       target: '所有公共密钥请求接口',
//       expected: '水平/垂直越权失败，严格控制隔离域。',
//       steps: ['用普通用户 Token 访问应被 403 拦截', '记录响应体中的权限不足反馈']
//     }
//   ]
// }
//
// === 重放 / 篡改 / 越权攻击 (generate + lifecycle) ===
// 这些攻击在 PS1 中已有完整实现，封存备用。
//
// { caseId: 'generate-replay',    title: '密钥生成重放攻击',     PS1: Run-GenerateReplay }
// { caseId: 'generate-tamper',    title: '生成参数篡改（空UA/短UA/错误前缀）', PS1: Run-GenerateTamper }
// { caseId: 'generate-privilege', title: '生成越权访问',         PS1: Run-GeneratePrivilege }
// { caseId: 'lifecycle-replay',   title: '更新重放攻击',         PS1: Run-LifecycleReplay }
// { caseId: 'lifecycle-tamper',   title: '更新篡改攻击',         PS1: Run-LifecycleTamper }
// { caseId: 'lifecycle-privilege',title: '更新越权攻击',         PS1: Run-LifecyclePrivilege }
