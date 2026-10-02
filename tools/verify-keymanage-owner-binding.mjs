// =============================================================================
// tools/verify-keymanage-owner-binding.mjs
// -----------------------------------------------------------------------------
// 回归验证：POST /lifecycle/keymanage 的属主只能来自令牌。
//
// 背景：该接口原先只在请求体**没带** userId 时才回填当前用户，于是任何登录用户
// 都能把新密钥记在别人名下。修复后规则为：
//   * 非管理员 —— 属主强制取自令牌，请求体里的 userId/userName 一律忽略；
//   * 管理员   —— 允许代建，但目标账号必须真实存在；
//   * 创建响应 —— 与详情接口同口径脱敏（格算法的完整私钥不再从创建响应返回）。
//
// 凭据从环境变量或命令行取，不写进仓库：
//   PORTAL_ORIGIN / PORTAL_API_BASE / PORTAL_ADMIN_USER / PORTAL_ADMIN_PASSWORD
//   PORTAL_NODE_USER / PORTAL_NODE_PASSWORD
//
// 用法：
//   node tools/verify-keymanage-owner-binding.mjs \
//     --admin-user admin --admin-password *** --node-user yx --node-password ***
// =============================================================================
import { login } from './lib/captcha.mjs'

const argv = process.argv.slice(2)
function option(name, fallback = '') {
  const index = argv.indexOf(`--${name}`)
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback
}
const envFirst = (...names) => names.map(name => process.env[name]).find(Boolean) || ''

const ORIGIN = option('origin', envFirst('PORTAL_ORIGIN', 'KMS_PORTAL_ORIGIN') || 'http://127.0.0.1').replace(/\/$/, '')
const API_BASE = option('api-base', envFirst('PORTAL_API_BASE', 'KMS_PORTAL_API_BASE') || '/lifecycle-api')
const ADMIN_USER = option('admin-user', envFirst('PORTAL_ADMIN_USER', 'KMS_ADMIN_USER'))
const ADMIN_PASSWORD = option('admin-password', envFirst('PORTAL_ADMIN_PASSWORD', 'KMS_ADMIN_PASSWORD'))
const NODE_USER = option('node-user', envFirst('PORTAL_NODE_USER', 'KMS_NODE_USER'))
const NODE_PASSWORD = option('node-password', envFirst('PORTAL_NODE_PASSWORD', 'KMS_NODE_PASSWORD'))

const STAMP = `ownerfix-${Date.now().toString(36).toUpperCase().slice(-6)}`
// uA 必须是**真实在 sm2p256v1 上的点** —— KGC 会校验曲线方程，随手填
// '04'+'ab'*64 会被拒，报错还发生在建密钥那一步，看不出是 uA 的问题。
// 这里沿用 tools/verify-keyvalue-redaction.mjs 里已验证可用的一份。
const UA = '04b038bd3450aff1c985e74918f6aeac37a6c05193c9c68654ab02dad094279177e8d692af475613983366ea67abc310e75b3c1fbe1ae51d4dda1519762f8e1b2e'

let failures = 0
function check(label, ok, detail) {
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? `  -> ${detail}` : ''}`)
  if (!ok) failures += 1
}

async function api(path, { method = 'GET', token, body } = {}) {
  const res = await fetch(`${ORIGIN}${API_BASE}${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {})
    },
    ...(body ? { body: JSON.stringify(body) } : {})
  })
  return { status: res.status, json: await res.json().catch(() => null) }
}

/** 新密钥的字段：算法可选，便于分别验证"属主可见材料"与"格算法一律脱敏"。 */
function newKeyPayload(encrytName) {
  return {
    encrytType: '无证书非对称加密',
    encrytName,
    keyName: `${STAMP}-${encrytName}`,
    keyUse: 'verify',
    keyDomain: 'A',
    status: '0',
    ua: UA
  }
}

async function createAs(token, payload, owner) {
  return api('/lifecycle/keymanage', {
    method: 'POST',
    token,
    body: { ...payload, ...owner }
  })
}

const created = []

async function main() {
  console.log(`\n=== 属主绑定回归（${ORIGIN}${API_BASE}）===`)

  if (!ADMIN_USER || !ADMIN_PASSWORD || !NODE_USER || !NODE_PASSWORD) {
    console.error('缺少凭据：请提供 --admin-user/--admin-password 与 --node-user/--node-password（或对应环境变量）')
    process.exit(2)
  }

  const adminToken = await login(ORIGIN, API_BASE, ADMIN_USER, ADMIN_PASSWORD)
  const nodeToken = await login(ORIGIN, API_BASE, NODE_USER, NODE_PASSWORD)

  const adminInfo = await api('/getInfo', { token: adminToken })
  const nodeInfo = await api('/getInfo', { token: nodeToken })
  const adminId = adminInfo.json?.user?.userId
  const nodeId = nodeInfo.json?.user?.userId
  check('两个主体都能取到身份', Boolean(adminId && nodeId), `admin=${adminId} node=${nodeId}`)
  check('节点账号确实不是管理员', Number(nodeId) !== 1, `node userId=${nodeId}`)

  // ---------------------------------------------------------------------
  // 1. 非管理员伪造他人属主 → 必须被令牌身份覆盖
  // ---------------------------------------------------------------------
  console.log('\n=== 1. 非管理员伪造 userId/userName ===')
  const spoofed = await createAs(nodeToken, newKeyPayload('SM2'), {
    userId: Number(adminId),
    userName: ADMIN_USER
  })
  const spoofedKey = spoofed.json?.data
  check('创建请求被接受（不是 500）', spoofed.status === 200, `HTTP ${spoofed.status} ${spoofed.json?.msg || ''}`)
  check('★ 属主被强制改写为令牌持有者', Number(spoofedKey?.user_id ?? spoofedKey?.userId) === Number(nodeId),
    `请求声称 userId=${adminId}，实际写入 userId=${spoofedKey?.user_id ?? spoofedKey?.userId}`)
  check('★ 属主名同样来自令牌', (spoofedKey?.user_name ?? spoofedKey?.userName) === NODE_USER,
    `请求声称 userName=${ADMIN_USER}，实际写入 userName=${spoofedKey?.user_name ?? spoofedKey?.userName}`)
  if (spoofedKey?.key_id ?? spoofedKey?.keyId) created.push(spoofedKey.key_id ?? spoofedKey.keyId)

  // ---------------------------------------------------------------------
  // 2. 非管理员即使不伪造，也只落在自己名下
  // ---------------------------------------------------------------------
  console.log('\n=== 2. 非管理员正常创建 ===')
  const own = await createAs(nodeToken, newKeyPayload('SM2'), {})
  const ownKey = own.json?.data
  check('属主为令牌持有者', Number(ownKey?.user_id ?? ownKey?.userId) === Number(nodeId),
    `userId=${ownKey?.user_id ?? ownKey?.userId}`)
  if (ownKey?.key_id ?? ownKey?.keyId) created.push(ownKey.key_id ?? ownKey.keyId)

  // ---------------------------------------------------------------------
  // 3. 管理员代建仍然可用（脚本与运维依赖这条路径）
  // ---------------------------------------------------------------------
  console.log('\n=== 3. 管理员代建 ===')
  const onBehalf = await createAs(adminToken, newKeyPayload('SM2'), {
    userId: Number(nodeId),
    userName: NODE_USER
  })
  const onBehalfKey = onBehalf.json?.data
  check('★ 管理员可为他人代建', Number(onBehalfKey?.user_id ?? onBehalfKey?.userId) === Number(nodeId),
    `HTTP ${onBehalf.status} userId=${onBehalfKey?.user_id ?? onBehalfKey?.userId}`)
  if (onBehalfKey?.key_id ?? onBehalfKey?.keyId) created.push(onBehalfKey.key_id ?? onBehalfKey.keyId)

  // ---------------------------------------------------------------------
  // 4. 管理员指定不存在的属主 → 显式报错，而不是外键失败
  // ---------------------------------------------------------------------
  console.log('\n=== 4. 管理员指定不存在的属主 ===')
  const bogus = await createAs(adminToken, newKeyPayload('SM2'), {
    userId: 99999999,
    userName: 'ghost'
  })
  const bogusMsg = String(bogus.json?.msg || '')
  check('★ 不存在的属主被拒绝', bogus.json?.code !== 200 && /属主不存在/.test(bogusMsg),
    `code=${bogus.json?.code} msg=${bogusMsg || '(空)'}`)

  // ---------------------------------------------------------------------
  // 5. 创建响应的脱敏口径
  //    SM2 属主应拿到自己的材料；格算法的完整私钥任何情况都不返回。
  // ---------------------------------------------------------------------
  console.log('\n=== 5. 创建响应脱敏 ===')
  const lattice = await createAs(adminToken, newKeyPayload('CL-Falcon'), { userId: Number(adminId), userName: ADMIN_USER })
  const latticeKey = lattice.json?.data
  const latticeValue = String(latticeKey?.key_value ?? latticeKey?.keyValue ?? '')
  check('★ 格算法（CL-Falcon）创建响应不含完整私钥',
    latticeValue.includes('redacted') || !/private_key/i.test(latticeValue),
    latticeValue ? latticeValue.slice(0, 90) : '(空)')
  if (latticeKey?.key_id ?? latticeKey?.keyId) created.push(latticeKey.key_id ?? latticeKey.keyId)

  const sm2Owned = String(ownKey?.key_value ?? ownKey?.keyValue ?? '')
  check('SM2 属主仍能在创建响应拿到自己的材料（KGC 流程需要）',
    sm2Owned.includes('partialKey') || sm2Owned.includes('finalPublicKey'),
    sm2Owned ? sm2Owned.slice(0, 90) : '(空)')

  console.log(`\n=== 结果：${failures === 0 ? 'ALL PASS' : `${failures} 项失败`} ===`)
  console.log(`本次新建的测试密钥 keyId：${created.length ? created.join(', ') : '(无)'}（均为 ${STAMP} 前缀，可自行回收）`)
  process.exit(failures === 0 ? 0 : 1)
}

main().catch(error => {
  console.error(`验证脚本异常：${error?.message || error}`)
  process.exit(2)
})
