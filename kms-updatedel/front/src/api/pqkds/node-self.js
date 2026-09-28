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
