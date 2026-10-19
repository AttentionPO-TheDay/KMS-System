const probe = (caseId, title, target, expected, steps) => ({ caseId, title, target, expected, steps, mode: '实际协议探针 · 独立临时会话' })
export const securitySuites = [
  { id: 'generation-protocol', name: '密钥生成协议校验', accent: 'accent-red',
    summary: '针对现有双份额生成签发入口，只发送非法请求。先后验证合法节点读取，不登记或改变业务密钥。',
    cases: [
      probe('generation-identity-injection', '伪造生成节点身份', '签发接口的可信身份与字段白名单', '客户端注入 nodeId 应返回 INVALID_PARAMETER，身份只能由服务端会话决定。', ['建立独立节点会话', '注入 foreign-node 身份', '核对拒绝码与合法读取']),
      probe('generation-unknown-algorithm', '未授权算法替换', '生成签发算法白名单', '替换为 RSA-512 必须返回 KEYGEN_SCHEME_INVALID。', ['发送 RSA-512 签发请求', '核对方案拒绝码', '确认合法读取正常']),
      probe('generation-malformed-json', '生成请求格式破坏', '签发接口 JSON 对象解析', '残缺 JSON 必须返回 INVALID_PARAMETER，500 或接口不存在不算通过。', ['发送残缺 JSON', '核对参数拒绝码', '确认服务可读取']),
      probe('generation-invalid-version', '密钥版本类型混淆', '密钥版本必须为正整数', 'keyVersion=1.5 必须返回 INVALID_PARAMETER，不能截断为版本1后签发。', ['提交非整数版本', '核对版本拒绝码', '确认合法读取正常'])
    ] },
  { id: 'pq-protocol', name: '抗量子生成协议安全', accent: 'accent-purple',
    summary: '4个场景覆盖参数白名单、私密字段禁入、来源存在性3条协议规则。参数降级与参数混用共用规则；本组不作为抗量子算法安全通过的依据。',
    cases: [
      probe('pq-parameter-downgrade', '封装参数集降级', '改进型双份额密钥封装签发参数', 'variant=128 不在支持的参数集中，必须返回 INVALID_PARAMETER。功能关闭不算通过。', ['使用 KYBER 内部标识提交 variant=128', '核对参数拒绝码', '确认节点读取正常']),
      probe('pq-sign-encrypt-confusion', '签名与封装参数混用', '标准签名家族与封装家族参数区分', 'FALCON 签名家族必须拒绝封装家族的 variant=768。本项只验证签发参数，不证明密文安全。', ['对签名家族提交 variant=768', '核对 INVALID_PARAMETER', '确认节点读取正常']),
      probe('pq-secret-upload', '向公钥协议注入私密材料', '签发入口私密字段禁入策略', '包含 secretKey 的请求必须返回 INVALID_PARAMETER；只用虚构字符串，不读取或上传真实私钥。', ['注入虚构 secretKey', '核对拒绝码', '证据只记录状态与拒绝码，不记录材料']),
      probe('pq-issuance-source-forgery', '伪造签发来源替换引用', '双份额生成来源替换约束', '虚构 abandonGenerationIssuanceId 必须返回 KEYGEN_ISSUANCE_CONFLICT，不得创建或替换签发来源。', ['提交虚构来源引用', '核对来源冲突码', '确认合法读取正常'])
    ] },
  { id: 'passwordless-boundary', name: '无密码会话与网络边界', accent: 'accent-orange',
    summary: '针对实际 Demo 会话、CSRF、revision 与节点/管理员权限，不再测试密码登录或验证码。',
    cases: [
      probe('network-session-forgery', '伪造演示会话', '节点身份读取接口', '虚构 Cookie 必须被判为 DEMO_CONTEXT_STALE。', ['建立合法对照', '用伪造 Cookie 读取身份', '核对拒绝码并验证合法对照']),
      probe('network-csrf', '伪造 CSRF 凭据', '节点切换管理端接口', '错误 CSRF 必须返回 DEMO_CSRF_INVALID，原节点身份不变。', ['建立独立节点会话', '错误 CSRF 请求管理端切换', '确认拒绝且原节点可读取']),
      probe('network-stale-revision', '旧会话版本重放', '会话变更 revision 栅栏', '旧 revision 必须返回 DEMO_REVISION_STALE。', ['建立当前版本会话', '用上一版本请求切换管理端', '确认旧版本被拒绝']),
      probe('network-role-isolation', '节点访问管理员接口', '管理员用户查询权限', '节点不能读取管理员用户数据，应返回 DEMO_FORBIDDEN。', ['建立节点会话', '访问 admin/users', '核对权限拒绝码']),
      probe('network-origin', '跨来源会话变更', '实际演示入口 Origin 校验', '不受信任的 Origin 必须返回 DEMO_ORIGIN_REJECTED。', ['建立节点会话', '外部 Origin 请求切换管理端', '确认拒绝且原身份可读取']),
      probe('network-missing-session', '无会话读取节点资料', '节点接口拒绝匿名访问', '完全不携带会话 Cookie 的请求必须返回 DEMO_CONTEXT_STALE。', ['保留合法对照会话', '不带Cookie访问节点资料', '确认拒绝且合法会话正常'])
    ] }
]
export const securityAssets = [
  { name: '当前系统安全测试方案', path: 'doc/system-security-test-plan.md', desc: '14 个固定协议探针、前置条件、判定标准和未覆盖范围。' },
  { name: '实际测试实现', path: 'kms-acceptance/backend/system_security.go', desc: '无密码会话与生成协议的非破坏性测试，旧密码脚本不再路由。' }
]
