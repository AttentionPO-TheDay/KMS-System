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
        mode: 'Postman',
        target: '伪造不在曲线上的点、错误长度、错误前缀',
        expected: '非法公钥点、非法长度或前缀（如05）应在协议层直接被拒绝。',
        steps: ['篡改公钥使其不在椭圆曲线上', '将公钥长度改为 64 字符重发', '将公钥前缀从 04 改为 05 重发']
      },
      {
        caseId: 'algo-weak-param',
        title: '弱算法降级攻击',
        mode: 'Postman',
        target: '请求极短的密钥长度或废弃算法',
        expected: '后台密码模块应强制拒绝不安全参数，不再生成低强度密钥。',
        steps: ['发起密钥生成请求，指定极低位数的弱参数', '修改请求体试图降级为不安全的废弃哈希算法']
      },
      {
        caseId: 'algo-malformed',
        title: '畸形密码载荷攻击',
        mode: 'Postman攻击',
        target: '解析器健壮性：破坏格式边界',
        expected: '算法解析器不应抛出内存溢出或拒绝服务，应安全拦截。',
        steps: ['在需要十六进制或 Base64 的密码参数中注入乱码', '破坏 ASN.1 或证书核心结构位导致解析偏移']
      }
    ]
  },
  {
    id: 'api-security',
    name: '业务接口 2 类攻击',
    accent: 'accent-blue',
    summary: '按通用 API 安全口径测试，包含对密钥操作请求的重放利用和越权数据访问。',
    cases: [
      {
        caseId: 'api-replay',
        title: '接口重放攻击',
        mode: 'Postman 导入',
        target: 'POST /keymanage/keymanage 生效鉴权',
        expected: '再次发送被拦截或记录重复，不应导致额外成功或异常错误。',
        steps: ['由于 cURL 复制了有效 Token，延迟后重放', '观察后端对旧请求和高频发送的重放防护']
      },
      {
        caseId: 'api-privilege',
        title: '业务越权访问',
        mode: '多用户 Token 互试',
        target: '所有公共密钥请求接口',
        expected: '水平/垂直越权失败，严格控制隔离域。',
        steps: ['用普通用户 Token 访问应被 403 拦截', '记录响应体中的权限不足反馈']
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
