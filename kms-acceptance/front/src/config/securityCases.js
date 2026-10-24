const probe = (caseId, title, target, expected, steps) => ({ caseId, title, target, expected, steps, mode: '协议测试' })
export const securitySuites = [
  { id: 'quantum-models', name: '量子攻击模型仿真与参数评估', cases: [
    { caseId: 'quantum-lwe-usvp', title: '原始格 uSVP 量子攻击模型仿真', mode: '攻击模型仿真' },
    { caseId: 'quantum-lwe-bdd', title: '原始格 BDD 量子攻击模型仿真', mode: '攻击模型仿真' },
    { caseId: 'quantum-lwe-dual', title: '对偶格量子攻击模型仿真', mode: '攻击模型仿真' }
  ] },
  { id: 'generation-protocol', name: '密钥生成协议校验', accent: 'accent-red',
    cases: [
      probe('generation-identity-injection', '伪造生成节点身份', '签发接口的可信身份与字段白名单', '客户端注入 nodeId 应返回 KEYGEN_IDENTITY_FIELD_FORBIDDEN，身份只能由服务端会话决定。', ['建立独立节点会话', '注入 foreign-node 身份', '核对拒绝码与合法读取']),
      probe('generation-unknown-algorithm', '未授权算法替换', '生成签发算法白名单', '替换为 RSA-512 必须返回 KEYGEN_SCHEME_INVALID。', ['发送 RSA-512 签发请求', '核对方案拒绝码', '确认合法读取正常']),
      probe('generation-malformed-json', '生成请求格式破坏', '签发接口 JSON 对象解析', '残缺 JSON 必须返回 KEYGEN_JSON_INVALID，500 或接口不存在不算通过。', ['发送残缺 JSON', '核对参数拒绝码', '确认服务可读取']),
      probe('generation-invalid-version', '密钥版本类型混淆', '密钥版本必须为正整数', 'keyVersion=1.5 必须返回 KEYGEN_VERSION_INVALID，不能截断为版本1后签发。', ['提交非整数版本', '核对版本拒绝码', '确认合法读取正常'])
    ] },
  { id: 'passwordless-boundary', name: '网络攻击', accent: 'accent-orange',
    cases: [
      probe('network-session-forgery', '伪造演示会话', '节点身份读取接口', '虚构 Cookie 必须被判为 DEMO_SESSION_INVALID。', ['建立合法对照', '用伪造 Cookie 读取身份', '核对拒绝码并验证合法对照']),
      probe('network-csrf', '伪造 CSRF 凭据', '节点切换管理端接口', '错误 CSRF 必须返回 DEMO_CSRF_INVALID，原节点身份不变。', ['建立独立节点会话', '错误 CSRF 请求管理端切换', '确认拒绝且原节点可读取']),
      probe('network-stale-revision', '旧会话版本重放', '会话变更 revision 栅栏', '旧 revision 必须返回 DEMO_REVISION_STALE。', ['建立当前版本会话', '用上一版本请求切换管理端', '确认旧版本被拒绝']),
      probe('network-role-isolation', '节点访问管理员接口', '管理员用户查询权限', '节点不能读取管理员用户数据，应返回 DEMO_FORBIDDEN。', ['建立节点会话', '访问 admin/users', '核对权限拒绝码']),
      probe('network-origin', '跨来源会话变更', '实际演示入口 Origin 校验', '不受信任的 Origin 必须返回 DEMO_ORIGIN_REJECTED。', ['建立节点会话', '外部 Origin 请求切换管理端', '确认拒绝且原身份可读取']),
      probe('network-missing-session', '无会话读取节点资料', '节点接口拒绝匿名访问', '完全不携带会话 Cookie 的请求必须返回 DEMO_SESSION_REQUIRED。', ['保留合法对照会话', '不带Cookie访问节点资料', '确认拒绝且合法会话正常'])
    ] }
]
export const securityAssets = [
  { name: '当前系统安全测试方案', path: 'doc/system-security-test-plan.md', desc: '密钥生成及会话边界协议探针、前置条件与判定标准。' },
  { name: '实际测试实现', path: 'kms-acceptance/backend/system_security.go', desc: '无密码会话与生成协议的非破坏性测试，旧密码脚本不再路由。' }
]
