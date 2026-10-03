/**
 * 验收脚本的**节点会话夹具**：建节点 → 激活 → 拿节点令牌（KMS-005）。
 *
 * 为什么要有这个文件
 * ------------------
 * 「管理员建节点 → 服务端给一次性激活凭证 → 节点本机生成设备密钥并激活换令牌」
 * 是 **KMS-005 之后唯一的节点登录方式**：节点账号的口令是随机生成、从不下发的
 * （见 `pqkds/node_account_service.py`），旧脚本里那句
 * `login(ORIGIN, '/updatedel-api', NODE_ID, 'admin123')` 已经**不可能成功**，
 * 而它失败的表现只是"令牌拿不到、后续全 401"，看日志像是接口挂了。
 *
 * 三个验收脚本都要走这条链路。各抄一遍的话，改一处要改三处，而漂移的表现是
 * "某个脚本突然建不出节点"，排查成本全花在找差异上 —— 与 `tools/lib/mysql.mjs`、
 * `utils/crypto/key-ref.js` 是同一条理由。
 *
 * Windows 上的两个坑（都踩过）
 * ---------------------------
 *   * Node 的 `execSync` 走 cmd.exe，PATH 里没有 `docker` —— 本文件不碰 docker，
 *     需要查库的脚本请用 `tools/lib/mysql.mjs`（它写死了 docker 的绝对路径）；
 *   * 浏览器 API 在 Node 里只有一半（有 `fetch`/`WebCrypto`，没有 IndexedDB）——
 *     由本文件统一 `import 'fake-indexeddb/auto'`，不给调用方"忘了 import"的机会。
 *     ⚠️ 这一步必须在**任何** src 模块被加载之前完成，所以它放在文件最顶上，
 *        且本文件对 src 模块一律用动态 import（静态 import 会被提升到它前面）。
 */

import 'fake-indexeddb/auto'

const { cryptoProvider } = await import('../../src/utils/crypto/browser-provider.js')
const { ensureDeviceKey, deviceFingerprint } = await import('../../src/utils/crypto/device-credential.js')
const { login } = await import('../../../../tools/lib/captcha.mjs')

/** 网关地址。与页面同源，才能保证"脚本测的"就是"用户点的"那一条路径。 */
export const ORIGIN = 'http://127.0.0.1'
/** 节点端 API 前缀（`urls.py`）。 */
export const PQKDS = `${ORIGIN}/pqkds-api/pqkds`
/** 管理端 API 前缀（登录、建节点走这条）。 */
export const UPDATEDEL_API = `${ORIGIN}/updatedel-api`

/**
 * 调一个 JSON 接口。**不抛错** —— 返回 `{status, body, headers}`，
 * 由调用方按自己的判据断言。"网络层失败"与"业务拒绝"在验收里是两回事，
 * 混成一个异常会让失败信息只剩一句 `fetch failed`。
 *
 * `headers` 是**响应头**（`Headers` 对象转成的普通对象）。加它是因为
 * 有的判据本来就在头部而不在 body 里 —— 例如弃用标记 `Deprecation: true`
 * （KMS-008 用它标旧用户腿接口）。把这类判据写成"读 body 里的某个字段"
 * 会让它与实现约定脱节。
 */
export async function api(base, path, { method = 'GET', token, body } = {}) {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    ...(body ? { body: JSON.stringify(body) } : {})
  })
  const headers = {}
  res.headers.forEach((value, name) => { headers[name.toLowerCase()] = value })
  return { status: res.status, body: await res.json().catch(() => null), headers }
}

/**
 * 业务成功的判据。
 *
 * ⚠️ 两套响应约定**并存且刻意不同**（见 `pqkds/api_contract.py` 的文件头）：
 *    * 节点端 `/node-self/*`：HTTP **恒 200**，成败只看 body 的 `code`；
 *    * 管理端：用真实 HTTP 状态码，body 的 `code` 是 2000。
 * 所以判据必须同时认 200 与 2000 —— 只看 HTTP 状态的检查在这里是恒真的。
 */
export const isOk = (body) => body?.code === 200 || body?.code === 2000

/** 段落标题，让输出能直接看出走到哪一步。 */
export const title = (text) => console.log(`\n=== ${text} ===`)

/**
 * 检查清单。每条都带**证据串**：验收报告的价值全在这里 ——
 * 只写 [FAIL] 而不写实际值，看的人还要自己复现一遍才能知道发生了什么。
 */
export function makeReporter() {
  const results = []
  const check = (name, pass, detail = '') => {
    results.push({ name, pass, detail })
    console.log(`  ${pass ? '[PASS]' : '[FAIL]'} ${name}${detail ? `  → ${detail}` : ''}`)
  }
  const info = (text) => console.log(`  [info] ${text}`)
  /** 收尾：打印汇总，任何一条不过就把进程标记为失败（CI 与人都靠这个退出码）。 */
  const finish = () => {
    const passed = results.filter((r) => r.pass).length
    console.log(`\n=== 结果：${passed}/${results.length} 项通过 ===`)
    if (passed !== results.length) {
      results.filter((r) => !r.pass).forEach((r) => console.log(`  - ${r.name}  ${r.detail}`))
      process.exitCode = 1
    }
    return { passed, total: results.length, results }
  }
  return { check, info, finish, results }
}

/** 管理员登录。返回令牌。 */
export async function adminLogin(username = 'admin', password = 'admin123') {
  return login(ORIGIN, '/updatedel-api', username, password)
}

// 同一毫秒内建多个节点时用序号错开 —— 只靠时间戳会在"连建两个节点"的脚本里撞号，
// 而重号的表现是"第二个节点建不出来"，与激活流程毫无关系，极易查错方向。
let seq = 0

/**
 * 建节点。返回 `{nodeId, name, activationCode}`。
 *
 * `activationCode` 是**明文只出现这一次**的凭证（库里存的是它的 sha256），
 * 所以这里拿到后必须直接交给 `activateNode`，不要落到日志里。
 */
export async function createNode(adminToken, {
  prefix = 'NV',
  name = '',
  nodeType = 'full',
  permissionLevel = 'L2',
  domainId = 'verify'
} = {}) {
  const seed = Date.now().toString(36).toUpperCase().slice(-6)
  const nodeId = `${prefix}-${seed}${(seq++).toString(36).toUpperCase()}`
  // ⚠️ IP/端口按 **nodeId 的哈希**派生，不用 Date.now()：服务端的节点注册有
  //    去重判定（重名/同址会**返回已存在的旧节点**且不给激活凭证），而
  //    Date.now() 取模的地址空间很窄 —— 一次中断的运行留下的节点会让
  //    后来的运行"建节点成功但没拿到激活凭证"，报错里却是另一个节点，
  //    看起来像注册接口坏了（KMS-015 施工时实测踩中一次）。
  //    nodeId 本身带时间戳与序号，按它哈希得到的地址跨运行几乎不会撞。
  //    ⚠️ 移位必须用 `>>>`（无符号）：`>>` 对 ≥2^31 的值给负数，拼出的
  //    地址会出现负段，服务端回"IP地址: 请输入一个有效的IPv4或IPv6地址"——
  //    看起来像注册接口的校验坏了。
  let hashish = 7
  for (const ch of nodeId) hashish = (hashish * 31 + ch.charCodeAt(0)) >>> 0
  const res = await api(PQKDS, '/nodes/register/', {
    method: 'POST',
    token: adminToken,
    body: {
      node_id: nodeId,
      name: name || nodeId,
      ip_address: `10.${(hashish % 200) + 20}.${((hashish >>> 8) % 200) + 20}.1`,
      port: 61000 + (hashish % 4000),
      node_type: nodeType,
      permission_level: permissionLevel,
      domain_id: domainId
    }
  })
  if (!isOk(res.body)) {
    throw new Error(`建节点失败（${nodeId}）：${res.body?.message || res.body?.msg || JSON.stringify(res.body)}`)
  }
  const data = res.body?.data || {}
  if (!data.activation_code) {
    throw new Error(`建节点成功但没拿到激活凭证（${nodeId}）：${JSON.stringify(data).slice(0, 200)}`)
  }
  return { nodeId, name: name || nodeId, activationCode: data.activation_code }
}

/**
 * 激活：本机生成设备密钥 → 用激活凭证换令牌。返回 `{token, fingerprint}`。
 *
 * ⚠️ `fingerprint` 是**设备公钥的指纹**（`sha256("{crv}|{x}|{y}")[:32]`），
 *    它就是服务端 `Node.key_device_id` 里记的东西（`node_auth_views._public_key_fingerprint`），
 *    也是登记公钥时该放进 `deviceId` 的值。
 *    旧脚本用的是 `store.getDeviceId()`（浏览器随机 id）—— 两者**不是一回事**，
 *    拿后者去比对永远不相等，而失败信息看起来像"设备绑定坏了"。
 */
export async function activateNode(nodeId, activationCode) {
  const { publicKeyJwk } = await ensureDeviceKey(nodeId)
  const res = await api(PQKDS, '/node-self/activate/', {
    method: 'POST',
    body: {
      nodeId,
      code: activationCode,
      devicePublicKey: publicKeyJwk,
      deviceAlgorithm: 'ECDSA-P256'
    }
  })
  if (!isOk(res.body)) {
    throw new Error(`激活失败（${nodeId}）：${res.body?.msg || JSON.stringify(res.body)}`)
  }
  return {
    token: res.body.data.token,
    name: res.body.data.name,
    fingerprint: await deviceFingerprint(nodeId)
  }
}

/** 建节点 + 激活，一步到位。返回 `{nodeId, name, activationCode, token, fingerprint}`。 */
export async function newNodeSession(adminToken, options = {}) {
  const created = await createNode(adminToken, options)
  const session = await activateNode(created.nodeId, created.activationCode)
  return { ...created, ...session }
}

/**
 * 二次登录：拿挑战 → 用设备私钥签 → 换令牌。
 *
 * 与 `activateNode` 的区别：激活是**一次性**的（凭证用完即焚），
 * 之后每次进站走的都是这里。
 *
 * ⚠️ 这里**不 import `src/api/pqkds/node-self.js`**：那个模块（乃至它上面的
 *    `@/api/pqkds/http`）用的是 Vite 的 `@/` 别名，Node 解析不了。
 *    而这几个请求的形状本来就很简单，直接用本文件的 `api()` ——
 *    顺带保证验收脚本走的是线上同一组路径与字段。
 */
export async function deviceLogin(nodeId) {
  const { signChallenge } = await import('../../src/utils/crypto/device-credential.js')
  const challenge = await api(PQKDS, `/node-self/challenge/?nodeId=${encodeURIComponent(nodeId)}`)
  if (!isOk(challenge.body)) {
    throw new Error(`取挑战失败（${nodeId}）：${challenge.body?.msg || JSON.stringify(challenge.body)}`)
  }
  const { challengeId, challenge: nonce } = challenge.body.data
  const signature = await signChallenge(nodeId, nonce)
  const res = await api(PQKDS, '/node-self/login/', {
    method: 'POST',
    body: { nodeId, challengeId, signature }
  })
  if (!isOk(res.body)) {
    throw new Error(`设备登录失败（${nodeId}）：${res.body?.msg || JSON.stringify(res.body)}`)
  }
  return { token: res.body.data?.token || '', nodeId: res.body.data?.nodeId, name: res.body.data?.name }
}

/** 供脚本引用：默认 provider 实例（省得每个脚本各 import 一次）。 */
export { cryptoProvider }
