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
 * @param {string} algorithm  SM2 / SSCL / KYBER / FALCON
 * @param {string} publicKey  **十六进制**。Kyber 由服务端按长度推断变体。
 * @param {string} [securityLevel]
 * @param {string} [deviceId] §4.4 设备绑定：本机 deviceId。
 *   服务端在**第一次**上报时记下它；后续上报若与已绑定的不一致会被拒
 *   （业务码 409）。那是可处置的状态，不是参数错。
 */
export function registerSelfNodePublicKey(algorithm, publicKey, securityLevel, deviceId) {
  return http
    .post('/node-self/keys/', { algorithm, publicKey, securityLevel, deviceId })
    .then(unwrap)
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
