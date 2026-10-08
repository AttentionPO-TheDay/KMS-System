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
 * 回收本节点的一把长期密钥（KMS-007）。
 *
 * ⚠️ `algorithm` / `keyId` / `keyVersion` **三者都必须给出**，而且是列表行上的原值。
 *    `keyId` 与 `keyVersion` 缺一不可：服务端**不接受**"取最新一把"的隐式行为
 *    （KMS-006 定下的纪律）——替调用方挑版本，挑中的那一版与页面上显示的可能
 *    不是同一个，而两边都不会报错。`algorithm` 同理**不再由服务端推断**：
 *    服务端查找的那一行是 `(节点, 算法, keyId, 版本)` 四元组，而 keyId 只是一段
 *    不透明文本，跨算法**没有**唯一性保证（同一台机器上两把不同算法的密钥
 *    可能碰巧同名）。少传一个字段不会退化成"全算法搜一遍"，只会被明确拒掉 ——
 *    那正是我们要的：宁可拒绝，也不要猜错算法撤掉另一把。
 *    列表页本来就逐行渲染了算法名，原样带回来即可。
 *
 * ⚠️ 回收是**终态**：该版本此后不能更新，也不能用于新分发/新签名/新预分配/
 *    新会话。回收入口还会处置受影响的对象（未消费池项、已建立会话），
 *    并把处理结果放在响应的 `impact` 里。
 *
 * 响应 `data` 形状（与后端线约定）：`{ revoked, impact: { poolItems, sessions } }`。
 * **影响面计数必须在页面上如实显示**，不能吞成一句"回收成功" ——
 * "密钥已回收、池项/会话却还活着"与"接口说一切正常"是同一类静默错误，
 * 正是 KMS-007 要消灭的。
 *
 * 失败形状与其它 node-self 接口一致：HTTP 恒 200，成败看 `code`；
 * 失败原因在 `error.errorCode`（`api_contract.ERR_*`），判断必须用它。
 *
 * @param {string} algorithm  列表行原样带来的算法（如 'KYBER' / 'FALCON'）
 * @param {string} keyId      列表行原样带来的 keyId
 * @param {number} keyVersion 列表行原样带来的版本（服务端下发的是数字）
 * @param {string} reason     回收原因，会写进 revokedReason
 */
export function revokeSelfNodePublicKey(algorithm, keyId, keyVersion, reason) {
  // 四个字段都**原样转发**，不在这里做 Number()/String() 归一：
  // 把认不出的版本转成 NaN，JSON 会把它序列化成 null —— 服务端读到的就是
  // "未提供版本"，一个编程错误会伪装成一次合法的缺版本请求，定位信息在
  // 本地就丢掉了。该拒绝的让服务端用明确错误码拒绝。
  return http.post('/node-self/keys/revoke/', { algorithm, keyId, keyVersion, reason }).then(unwrap)
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

/**
 * 我可以解封的**节点腿信封**列表（KMS-011 / §6.5）。
 *
 * 每项含 `envelopeId`（整数主键，verify/recover 都用它）、`envelope` 本体、
 * `keyHash`、有效期，以及 KMS-011 补上的两样定位信息：
 *   * `sessionId` / `sessionStatus` —— 这个批次对应的会话（旧流程的节点腿
 *     信封没有对应会话时为 null）；
 *   * `isRecipient` —— **我是不是收件方**。发送方自己的列表里也会出现这些
 *     信封（它是自己发的），但取信/验签/解封只对接收方有意义。
 *     页面按它决定显示"处理"还是"等待对方处理"，别让用户点了才发现 403。
 *
 * ⚠️ 已有 KMS-007 的回收闸门：本节点对应算法的长期密钥被回收/过期时，
 *    接口直接拒（`data.error_code` 是 KEY_REVOKED/KEY_EXPIRED），不是返回空列表。
 */
export function listSelfEnvelopes(options = {}) {
  const params = {}
  if (options.includeExpired) params.includeExpired = 1
  if (options.limit) params.limit = options.limit
  return http.get('/node-self/envelopes/', { params }).then(unwrap)
}

/**
 * 这条会话该用**哪两版密钥**验收/解封（KMS-011）。
 *
 * 返回 `{recipientKeyId, recipientKeyVersion, falconKeyId, falconKeyVersion,
 *       falconPublicKey, senderNodeId, proofMessage}` —— 都是分发时写进
 * 会话行的那一份记录，不是"当前生产版本"。缺值时**如实为 null**（历史会话），
 * 页面显示"—"，不编。
 *
 * ⚠️ `falconPublicKey` 是小写 hex（服务端归一过），正是 `cryptoProvider.verify`
 *    要的形状。用错编码的表现是"验签失败"，看起来像伪造。
 * ⚠️ 只有**接收方**能调（发送方不需要，第三方不该拿到这条映射）——
 *    越权返回 `data.error_code = NOT_SESSION_PARTY`。
 */
export function getSessionVersions(sessionId) {
  return http.post(`/node-self/sessions/${encodeURIComponent(sessionId)}/versions/`).then(unwrap)
}

/**
 * 回报"我在本机验签通过"（KMS-011）。服务端会**独立复核一次**再推进状态：
 * 通过 → 会话进入 `recipient_verified`；验不过 → `SIGNATURE_INVALID`，状态不动。
 *
 * 幂等：会话已越过这一步时如实回 ok（`advanced=false`），不回退状态。
 */
export function verifyEnvelope(envelopeId) {
  return http.post(`/node-self/envelopes/${encodeURIComponent(envelopeId)}/verify/`).then(unwrap)
}

/**
 * 回报"我在本机解封成功"（KMS-011）。会话进入 `key_recovered`。
 *
 * ⚠️ 顺序由服务端状态机强制：没先验签就回报解封 → `SESSION_STATE_INVALID`
 *    （`initiated → key_recovered` 不是合法边）。这不是刁难：验签与解封
 *    是两条证据，状态机要的就是"两件事都真的发生过"。
 * ⚠️ 这一步是**节点的声明**（服务端没有 K，无法独立验证）。真正的建立条件
 *    是后面双方 proof 一致 —— 页面上别把"已解封"说成"会话安全了"。
 */
export function recoverEnvelope(envelopeId) {
  return http.post(`/node-self/envelopes/${encodeURIComponent(envelopeId)}/recover/`).then(unwrap)
}

/**
 * 提交持有证明 `HMAC-SHA256(K, session_id)`（十六进制，64 字符）。
 *
 * ⚠️ proof 是**证明持有 K**，不是 K 本身 —— 服务端没有 K，也永远不该收到 K。
 *    用 `node-envelope.js` 的 `nodeProof()` 算，别自己拼字符串：
 *    与对方（或服务端未来的校验）差一个字节的编码口径，症状都是
 *    "双方证明不一致"，看起来像有一方拿错了密钥。
 */
export function confirmSelfSession(sessionId, proof) {
  return http.post(
    `/node-self/sessions/${encodeURIComponent(sessionId)}/confirm/`, { proof }
  ).then(unwrap)
}

/**
 * 关闭会话（KMS-012 / §16.4）。**终态，不可恢复** —— 要重新通信只能重新分发。
 *
 * 双方都可以关；关闭后该会话不再接受确认或状态变更
 * （再确认会拿到 `SESSION_TERMINAL`）。页面在关闭成功后应删除本机的会话
 * 密钥副本（`removeSessionSecret`）—— 服务端不知道谁的本机存了什么。
 *
 * ⚠️ 顺序：**先服务端关闭、后删本地**。反过来一旦关闭请求失败，本机就再也
 *    算不出 proof，而服务端那边会话还活着。
 */
export function closeSelfSession(sessionId) {
  return http.post(`/node-self/sessions/${encodeURIComponent(sessionId)}/close/`).then(unwrap)
}

// ---------------------------------------------------------------------------
// 节点多级授权（任务书「节点多级授权」）：名录 + 授权申请
// ---------------------------------------------------------------------------
// 流程：节点看到**全网**名录 → 选对端 → 申请 → 管理员审批 → 双向放行。
//
// ⚠️ 收到授权之前，`/node-self/peers/<节点>/keys/` 会回
//    `data.error_code = NOT_AUTHORIZED`（403）——那是**预期**，不是故障。
//    页面把它呈现成"尚未授权，可发起申请"，而不是一句红色的"加载失败"。

/**
 * 我的授权申请（我发起的 + 别人发来的）。
 *
 * @returns {Promise<{outgoing: object[], incoming: object[]}>}
 *   `outgoing` = 我发起、等管理员审批的；`incoming` = 别的节点想与我通信，
 *   我**无权批**（决定权在管理员），但看得见 —— 否则对方那边显示"待审批"、
 *   我这边一片空白，两边对不上。
 */
export function listSelfAuthorizationRequests() {
  return http.get('/node-self/authorization-requests/').then(unwrap)
}

/**
 * 全网节点名录（排除自己），每行带与我的授权关系。
 *
 * ⚠️ 只回**身份性字段**（编号/名字/状态/域/类型/等级）+ 关系；
 *    **不含** ip/端口/sys_user_id/公钥 —— 服务端刻意如此，页面别指望拿到。
 */
export function listNodeDirectory() {
  return http.get('/node-self/directory/').then(unwrap)
}

/**
 * 发起授权申请。
 *
 * @param {string} targetNodeId 目标节点的**业务编号**（`Node.node_id`，如 `Node-001`）
 * @param {string} reason 申请理由（审批人据此判断；服务端要求非空、≤200 字）
 *
 * 幂等由服务端保证：这一对节点已有待审批申请时回**同一条**（`created:false`），
 * 两个方向都已授权时回 `alreadyGranted:true` 且不建单。所以调用方不必自己防重
 * —— 重复提交不会产生第二条。
 */
export function requestNodeAuthorization(targetNodeId, reason) {
  return http.post('/node-self/authorization-requests/', { targetNodeId, reason }).then(unwrap)
}

/**
 * 撤回自己发起的待审批申请。
 *
 * ⚠️ 只能撤**自己发起**的、且仍在 `pending` 的：服务端按 requester 判定，
 *    被申请方（哪怕是对方节点）也撤不了。
 */
export function cancelNodeAuthorizationRequest(requestId) {
  return http.post(`/node-self/authorization-requests/${encodeURIComponent(requestId)}/cancel/`).then(unwrap)
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
