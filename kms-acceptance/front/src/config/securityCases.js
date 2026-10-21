const probe = (caseId, title, target, expected, steps) => ({ caseId, title, target, expected, steps, mode: '协议测试' })
export const securitySuites = [
  { id: 'generation-protocol', name: '密钥生成协议校验', accent: 'accent-red',
    cases: [
      probe('generation-identity-injection', '伪造生成节点身份', '签发接口的可信身份与字段白名单', '客户端注入 nodeId 应返回 KEYGEN_IDENTITY_FIELD_FORBIDDEN，身份只能由服务端会话决定。', ['建立独立节点会话', '注入 foreign-node 身份', '核对拒绝码与合法读取']),
      probe('generation-unknown-algorithm', '未授权算法替换', '生成签发算法白名单', '替换为 RSA-512 必须返回 KEYGEN_SCHEME_INVALID。', ['发送 RSA-512 签发请求', '核对方案拒绝码', '确认合法读取正常']),
      probe('generation-malformed-json', '生成请求格式破坏', '签发接口 JSON 对象解析', '残缺 JSON 必须返回 KEYGEN_JSON_INVALID，500 或接口不存在不算通过。', ['发送残缺 JSON', '核对参数拒绝码', '确认服务可读取']),
      probe('generation-invalid-version', '密钥版本类型混淆', '密钥版本必须为正整数', 'keyVersion=1.5 必须返回 KEYGEN_VERSION_INVALID，不能截断为版本1后签发。', ['提交非整数版本', '核对版本拒绝码', '确认合法读取正常'])
    ] },
  { id: 'pq-protocol', name: '抗量子算法与协议验证', accent: 'accent-purple',
    cases: [
      probe('pq-parameter-downgrade', 'KYBER 密文篡改与参数降级', 'KYBER-512/768/1024 原生封装与解封装', '拒绝码 KYBER_KEYGEN_VARIANT_INVALID 正确；正常封装、固定向量与独立 JS 互操作通过；篡改密文不能恢复原共享密钥。', ['验证参数降级拒绝及合法读取', '三个参数集逐项验证正常封装和互操作', '翻转密文1位，验证隐式拒绝并展示结果']),
      probe('pq-sign-encrypt-confusion', 'FALCON 消息篡改与参数混用', 'FALCON-512 原生签名与验签', '拒绝码 FALCON_KEYGEN_VARIANT_INVALID 正确；正常签名及独立 JS 签名可验证；保留签名并修改消息后验签失败。', ['验证参数混用拒绝及合法读取', '正常签名及独立 JS 签名验签', '修改消息，展示实际验签结果']),
      probe('pq-secret-upload', 'KYBER 错误私钥与私密字段注入', '独立临时密钥之间的共享密钥隔离', '拒绝码 KEYGEN_PRIVATE_MATERIAL_FORBIDDEN 正确；两套临时密钥正常对照通过；错误私钥不能恢复原共享密钥。', ['注入虚构 secretKey 并核对拒绝码', '各参数集生成两套临时密钥进行正常对照', '换错私钥，比较解封装结果']),
      probe('pq-issuance-source-forgery', 'FALCON 签名/公钥替换与来源伪造', '签名完整性与验签公钥绑定', '拒绝码 KEYGEN_ISSUANCE_CONFLICT 正确；正常及独立 JS 对照通过；篡改签名或替换公钥均须验签失败。', ['验证虚构来源拒绝且合法读取正常', '正常签名与独立 JS 互操作', '篡改签名、替换公钥，逐项核对验签拒绝'])
    ] },
  { id: 'passwordless-boundary', name: '无密码会话与网络边界', accent: 'accent-orange',
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
  { name: '当前系统安全测试方案', path: 'doc/system-security-test-plan.md', desc: '14 个固定协议探针、前置条件、判定标准和未覆盖范围。' },
  { name: '实际测试实现', path: 'kms-acceptance/backend/system_security.go', desc: '无密码会话与生成协议的非破坏性测试，旧密码脚本不再路由。' }
]
