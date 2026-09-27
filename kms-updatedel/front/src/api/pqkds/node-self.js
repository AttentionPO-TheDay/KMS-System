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
 * 首次登录后的四套基础密钥初始化（Kyber / SSCL / SM2 / Falcon）。
 *
 * ⚠️ 耗时 15~25 秒（Falcon 占大头）。调用方必须显示 loading 并抑制重复提交 ——
 * 后端是幂等的，但重复提交只会让用户白等。
 */
export function initSelfNodeKeys() {
  // 单条请求可能超过默认超时，这里显式放宽
  return http.post('/node-self/init/', null, { timeout: 180000 }).then(unwrap)
}
