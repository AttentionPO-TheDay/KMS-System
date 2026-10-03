import http, { unwrap } from '@/api/pqkds/http'

/**
 * 节点自助接口（阶段 2）。对应后端 `pqkds/node_self_views.py`。
 *
 * 身份**不由参数传递**：后端从 Authorization 令牌自省取得 `userId`，
 * 再经 `Node.sys_user_id` 映射到节点。所以这里没有任何 nodeId 参数 ——
 * 传了也不作数（后端不读），刻意如此以免让人误以为可以替别的节点操作。
 *
 * 走 `/pqkds-api/` 网关前缀，与「节点管理」「节点鉴权」同一套路数。
 */

/**
 * 后端 `api_contract.py` 的 `ERR_*` 常量里，**本模块的调用方需要分支处理**的几个。
 *
 * ⚠️ 只映射到这儿的几个，不做全量转发：全量抄一份就会与后端漂移，而漂移的表现是
 *    某个分支**永远不成立**（名字对不上），且不报错。要新增分支时，
 *    去 `api_contract.py` 取准确名字再往这里加。
 *
 * 这些值会出现在 `error.errorCode` 上（由 `@/api/pqkds/http` 的拦截器附上）。
 * 判断**必须**用它，不要匹配 `error.message` —— 文案随时会改。
 */
export const NODE_SELF_ERR = Object.freeze({
  /** 上报公钥的这台设备与节点已绑定的设备不是同一台 */
  DEVICE_MISMATCH: 'DEVICE_MISMATCH',
  /**
   * 版本对不上。三种触发，**下一步各不相同**，页面要按 msg 分辨而不是一律"重试"：
   *   * 同 (keyId, 版本) 已有另一把公钥（真冲突）；
   *   * 更新时版本倒退或跨版跳跃（只允许 = 最新 或 逐版 +1）；
   *   * 更新的 keyId 不是本算法当前生产那把 —— 放行就会把在产版本换成别的，
   *     而请求返回成功（阶段 2 判据②要防的正是这个）。
   */
  KEY_VERSION_MISMATCH: 'KEY_VERSION_MISMATCH',
  /**
   * 更新目标在本节点**没有**登记记录：调用方以为登记过、实际没成功
   * （或 keyId 报错了）。处置是回到"先登记"，不是重试更新。
   */
  KEY_NOT_FOUND: 'KEY_NOT_FOUND',
  /**
   * 更新目标**已回收**（终态）。回收后不能再更新 —— 否则审计里它带着
   * `revoked_at`、业务上却又能用，两个说法只有一个是真的。
   * 要恢复服务得在本机生成**新的 keyId** 后重新登记。
   */
  KEY_REVOKED: 'KEY_REVOKED',
  /** 参数非法（含 keyId 带空白、版本非 ≥1 整数、rotate 认不出的值等） */
  INVALID_PARAMETER: 'INVALID_PARAMETER',
  /** 算法名不在白名单（历史别名 `falcon_lattice` 之类会被拒） */
  ALGORITHM_NOT_ALLOWED: 'ALGORITHM_NOT_ALLOWED'
})

/** 当前登录账号对应的节点及其初始化状态。管理员账号会得到 mapped=false。 */
export function getSelfNode() {
  return http.get('/node-self/').then(unwrap)
}

/**
 * 登记一个算法的**公钥**（§4.4）。
 *
 * 私钥在节点浏览器产生并留在本地密钥库，服务端只收公钥。
 * 后端在入口处**显式拒绝**私钥样式的字段名 —— 所以这里绝不能顺手把
 * `privateKey` 一起塞进来，那会被拒，而且拒的理由与"密钥不对"很像。
 *
 * ⚠️ `keyId` / `keyVersion` **必须**传节点本地铸的那一份
 * （`cryptoProvider.generate()` 的返回值里就有）。
 * 服务端在缺省时会自己铸一个 keyId 并回传，那个 id 与节点本地 keyRef
 * `node/{节点}/{算法}/{keyId}/{版本}` 里的那一段**不是同一串** ——
 * 两边各自"登记成功"，只是从此谁也找不到谁。判据④（新逻辑密钥不复用旧
 * SM2/SSCL 的 `u`）正是靠"新 keyId 落成新的一行"来判定的。
 *
 * 不传 keyId 只在**旧调用方**（`views/nodeInit`）的历史路径里出现，
 * 那条路径依赖的是"同一把公钥重复上报是幂等无操作"。
 *
 * @param {string} algorithm  SM2 / SSCL / KYBER / FALCON
 * @param {string} publicKey  **十六进制**。Kyber 由服务端按长度推断变体。
 * @param {string} [securityLevel]
 * @param {string} [deviceId] §4.4 设备绑定：本机 deviceId。
 *   服务端在**第一次**上报时记下它；后续上报若与已绑定的不一致会被拒
 *   （业务码 409）。那是可处置的状态，不是参数错。
 * @param {string} [keyId] 节点本地铸的 keyId（原样上报，服务端不做 trim/归一）。
 * @param {number} [keyVersion] 与本地 keyRef 同一版本号。
 * @param {boolean} [rotate] **更新**（KMS-006）：`true` = "同一把逻辑密钥的新版本"，
 *   缺省/`false` = "这是我当前的公钥"（登记，或重复上报的幂等无操作）。
 *
 *   ⚠️ `rotate: true` 时 `keyId` 与 `keyVersion` **缺一不可**，而且 `keyVersion`
 *      必须是**本机已经封存好的那一版**（keyRef 末段就是它）。服务端不替调用方
 *      算版本：算出来的那一版与本地封存的可能不是同一个，于是本机多出一把永远
 *      用不上的私钥、而生产版本指向的 keyRef 在本机查不到 —— 两个失败都不报错。
 *
 *   ⚠️ 版本只允许"等于最新（重试）"或"逐版 +1"。回退、跨版、未登记、已回收都会被拒，
 *      分别对应 `KEY_VERSION_MISMATCH` / `KEY_NOT_FOUND` / `KEY_REVOKED`；
 *      另有一个"非生产的 keyId"也报 `KEY_VERSION_MISMATCH`（见 NODE_SELF_ERR 的说明）。
 */
export function registerSelfNodePublicKey(
  algorithm,
  publicKey,
  securityLevel,
  deviceId,
  keyId,
  keyVersion,
  rotate
) {
  const payload = { algorithm, publicKey, securityLevel, deviceId }
  // 只在这两个字段**真的有值**时带上：显式传 `keyId: undefined` 会被
  // JSON.stringify 丢掉（无害），但传 `keyVersion: ''` 不会 —— 而空串在服务端
  // 是"未提供"（收敛为 1），与本地 ref 的 `/1` 一致，所以这里不额外兜底。
  if (keyId !== undefined && keyId !== null && keyId !== '') payload.keyId = String(keyId)
  if (keyVersion !== undefined && keyVersion !== null && keyVersion !== '') {
    payload.keyVersion = keyVersion
  }
  // ⚠️ 只在**真的要更新**时才带这个字段。另外两个调用点（`views/nodeInit` 的旧式
  //    无 keyId 路径、`views/generate/create` 的六参数位置参数调用）不传它，
  //    请求体必须一字不变 —— KMS-005 的验收脚本按逐字节比对走生成页那条路径。
  //    服务端缺省即 False，显式带 false 与不带是同一语义，没必要多写一个字段；
  //    而传 `rotate: undefined` 虽会被 JSON.stringify 丢掉，读代码的人却要多想一层。
  if (rotate === true) payload.rotate = true
  return http.post('/node-self/keys/', payload).then(unwrap)
}

/**
 * 本节点已登记的公钥列表（§4.4 / KMS-005）。
 *
 * 与 `/admin/node-long-term-keys/` 的区别：那个是**管理端跨节点**的登记历史，
 * 这个只答"我自己这个节点现在有哪些版本"。节点侧页面用它做「本地 vs 服务端」
 * 对照 —— 只有这个接口能回答"服务端记下的那把，是不是我本地这把"。
 *
 * 响应用的是 node-self 命名空间的约定（`{'code','msg','data'}` + HTTP 恒 200），
 * 所以调用方**不能**看 HTTP 状态判断成败，必须看 `code`。
 *
 * ⚠️ **没有筛选参数**，且是刻意的：后端这个 GET **不读任何 query**
 *    （`node_self_views.node_self_keys` 忽略 request.GET，一律返回本节点全部行，
 *    含被取代/已回收的历史版本）。给一个"能传 algorithm/status"的签名等于
 *    造一个**静默无效**的接口面 —— 传了不生效、还不报错，页面会显示成
 *    "筛完就这些"，而用户以为自己筛过了。
 *    页面需要筛选时在本地筛已载入的全量数据（数据量本来就是这个节点的密钥数）。
 */
export function listSelfNodeKeys() {
  return http.get('/node-self/keys/').then(unwrap)
}

/**
 * 首次登录后的初始化**收尾**。
 *
 * ⚠️ §4.4 起本接口**不再生成密钥** —— 它只校验四套公钥是否齐备，
 *    齐了就把节点置为 ACTIVE。密钥的产生在前端（`cryptoProvider.generate`），
 *    见 `views/nodeInit/index.vue`。
 *
 * 因此它现在**很快**（不再有 Falcon 的 15~25 秒），
 * 调用方真正需要 loading 的是前面的密钥生成。
 */
export function initSelfNodeKeys() {
  return http.post('/node-self/init/', null, { timeout: 60000 }).then(unwrap)
}

/**
 * 本节点**参与**的会话列表（文档 §10.10）。
 *
 * ⚠️ 用这个，不要用 `@/api/pqkds/distribution` 的 `listSessions()` 再在前端过滤。
 * 那个接口返回**全系统**会话，而且 node1/node2 序列化出来的是节点**名字**，
 * 与前端手上的 `nodeId`（业务编号 Node.node_id）**不是同一列**。
 * 拿 nodeId 去比名字要么永远不等（页面空白）、要么靠重名撞对（串号），
 * 两种失败都不报错。隔离由服务端按外键主键完成，前端只负责取。
 *
 * 返回项的 `senderNode` / `recipientNode` 是**显示名**，仅用于展示。
 *
 * @param {{includeExpired?: boolean, limit?: number}} [options]
 */
export function listSelfSessions(options = {}) {
  const params = {}
  if (options.includeExpired) params.includeExpired = 1
  if (options.limit) params.limit = options.limit
  return http.get('/node-self/sessions/', { params }).then(unwrap)
}

// ---------------------------------------------------------------------------
// 设备凭据认证（文档 §3 激活 / §5 登录）
// ---------------------------------------------------------------------------
// ⚠️ 这三个接口与上面几个的**根本区别**：上面都要求已登录（带令牌），
//    下面三个恰恰是**用来产生令牌**的，所以**不带令牌**调用。
//    `@/api/pqkds/http` 的请求拦截器会自动加 Authorization —— 这里没关系，
//    服务端不读它（`node_auth_views` 里这三个视图没有 `require_kms_user`）。

/**
 * 首次激活：节点名 + 一次性激活凭证 → 登记设备公钥 + 换发登录令牌。
 *
 * @param {{nodeId: string, code: string, devicePublicKey: object, deviceAlgorithm?: string}} payload
 * @returns {Promise<{token: string, nodeId: string, name: string}>}
 */
export function activateNode(payload) {
  return http.post('/node-self/activate/', payload).then(unwrap)
}

/**
 * 取一次性登录挑战。
 *
 * 挑战由**服务端**生成 —— 客户端可控的挑战等于没有挑战
 * （攻击者固定一个已知值就能重放抓到的签名）。
 */
export function getNodeChallenge(nodeId) {
  return http.get('/node-self/challenge/', { params: { nodeId } }).then(unwrap)
}

/**
 * 挑战-应答登录：用设备私钥签名换令牌。
 *
 * @param {{nodeId: string, challengeId: string, signature: string}} payload
 * @returns {Promise<{token: string, nodeId: string, name: string}>}
 */
export function loginWithDevice(payload) {
  return http.post('/node-self/login/', payload).then(unwrap)
}
