export const securitySuites = [
  {
    id: 'generate-attacks',
    name: '生成系统 3 类攻击',
    accent: 'accent-red',
    summary: '按验收口径展示生成系统 3 类攻击：重放、篡改、越权，重点验证密钥生成入口与用户态访问边界。',
    cases: [
      {
        caseId: 'generate-replay',
        title: '重放攻击',
        mode: '浏览器 + Postman',
        target: 'POST 生成请求',
        expected: '重复发送不应造成不可控重复有效业务结果。',
        steps: ['登录 testuser 并在用户密钥页抓取生成请求', 'Copy as cURL 后延迟 5 秒再重放']
      },
      {
        caseId: 'generate-tamper',
        title: '篡改攻击',
        mode: 'Postman',
        target: '公钥内容、公钥长度、公钥前缀',
        expected: '非法公钥、非法长度、非法前缀应被拒绝。',
        steps: ['将合法公钥改成非法曲线点', '分别改成 64 长度和 05 前缀重发']
      },
      {
        caseId: 'generate-privilege',
        title: '越权攻击',
        mode: '双 Token 对照',
        target: '公共密钥列表、非本人数据访问',
        expected: '普通用户不能访问管理员口径数据或他人密钥。',
        steps: ['分别登录普通用户与管理员获取 JWT', '用普通用户 Token 访问高权限接口']
      }
    ]
  },
  {
    id: 'lifecycle-attacks',
    name: '更新与回收 5 类攻击',
    accent: 'accent-orange',
    summary: '按验收口径展示更新与回收系统 5 类攻击：SQL 注入、XSS、重放、篡改、越权。',
    cases: [
      {
        caseId: 'lifecycle-sql',
        title: 'SQL 注入',
        mode: '半自动',
        target: '我的密钥、结果查询、操作记录查询条件',
        expected: '仅返回正常参数校验或空结果，不应出现异常 SQL 行为。',
        steps: ['对 keyName、actionType、record query 注入 SQL payload', '检查响应和列表结果是否异常']
      },
      {
        caseId: 'lifecycle-xss',
        title: 'XSS',
        mode: '半自动',
        target: '更新时可编辑的 keyName、keyUse、keyDomain',
        expected: '恶意脚本不应在我的密钥、详情、结果页执行。',
        steps: ['提交带 script/onload payload 的更新请求', '刷新列表和详情页确认仅文本显示']
      },
      {
        caseId: 'lifecycle-replay',
        title: '重放攻击',
        mode: '浏览器 + Postman',
        target: 'UPDATE_KEY / REVOKE_KEY 请求',
        expected: '重复请求不应造成越权或失控状态流转。',
        steps: ['抓取更新或回收请求', '延迟后重放并检查结果记录与状态变化']
      },
      {
        caseId: 'lifecycle-tamper',
        title: '篡改攻击',
        mode: 'Postman',
        target: 'keyId、user、body 字段',
        expected: '伪造用户、伪造 keyId、非法字段组合应被拒绝或无效。',
        steps: ['将 keyId 改为他人密钥或不存在的 key', '篡改 user、autoUpdate、domain 后重发']
      },
      {
        caseId: 'lifecycle-privilege',
        title: '越权攻击',
        mode: '双 Token 对照',
        target: '他人密钥更新与回收',
        expected: '普通用户不能操作他人 key，403/业务拒绝应可见。',
        steps: ['使用普通用户 Token 对 foreign key 发更新/回收', '验证返回和结果记录']
      }
    ]
  },
  {
    id: 'platform-protection',
    name: '平台防护验证',
    accent: 'accent-purple',
    summary: '验证扫描器拦截、登录暴破、点击劫持等平台级能力，和业务攻击区分展示。',
    cases: [
      {
        title: '扫描工具识别',
        mode: '自动化脚本',
        target: 'SmartSecurityFilter',
        expected: '恶意 User-Agent 访问应返回 403，后续访问进入黑名单窗口。',
        steps: ['运行 security/security_test.ps1', '观察 sqlmap User-Agent 探测返回码']
      },
      {
        title: '登录暴力破解',
        mode: '自动化脚本',
        target: '登录限流与锁定',
        expected: '连续 5 次错误后，第 6 次仍处于锁定窗口。',
        steps: ['脚本模拟 6 次错误登录', '检查锁定提示与 Redis 计数效果']
      },
      {
        title: '点击劫持',
        mode: '自动化 + 浏览器',
        target: '响应头与 iframe 嵌套行为',
        expected: '当前基线为 SAMEORIGIN；若要求更严，需要后续收紧为 deny/frame-ancestors none。',
        steps: ['检查 X-Frame-Options/CSP 响应头', '使用 iframe 页面嵌套验证']
      }
    ]
  }
]

export const securityAssets = [
  { name: '安全测试总方案', path: 'doc/security-test-plan.md', desc: '覆盖攻击范围、执行方式、预期结果与后续加固建议。' },
  { name: '自动化脚本入口', path: 'security/security_test.ps1', desc: '包含扫描器探测、登录暴破、点击劫持响应头检查等基线脚本。' }
]
