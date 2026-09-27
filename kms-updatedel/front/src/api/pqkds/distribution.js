import http, { unwrap, unwrapList } from '@/api/pqkds/http'

/**
 * 分发功能接口（从分发模块「复用」到管理端）。
 *
 * 边界说明：这些数据住在分发模块（Django / falcon_kds），管理端**不复制**它的库，
 * 只是它的调用方 —— 与「节点管理」「节点分发授权」同一套路数，都走 `/pqkds-api/`。
 * 复用的是**功能与数据**，不是它那套页面和登录：管理端用自己的登录态直接调这些接口，
 * 因此不存在第二个登录界面。
 *
 * 信封与成功码的不一致（200 / 2000 并存）统一由 `@/api/pqkds/http` 处理。
 */

// ---------------------------------------------------------------- 密钥池

/** 预分配密钥列表 */
export function listKeyPool(params) {
  return http.get('/key-pool/', { params: { page: 1, limit: 500, ...(params || {}) } }).then(unwrapList)
}

/** 密钥池统计（总数 / 未用 / 已用 / 过期 / 按算法分布） */
export function getKeyPoolStats(params) {
  return http.get('/key-pool/stats/', { params: params || undefined }).then(unwrap)
}

/**
 * 生成一批单向密钥池并下发给发送方节点。
 * 服务端用**发送方节点的 Kyber 公钥**加密，只有该节点能解开 —— 所以发送方节点
 * 必须已经有 Kyber 密钥（「节点管理」里新建节点时会一并生成）。
 */
export function distributeKeyPool(data) {
  return http.post('/key-pool/distribute/', data).then(unwrap)
}

/**
 * 生成节点间预分配密钥池（**支持 Falcon 格密码**）。
 *
 * 与上面 `distributeKeyPool` 的区别（两条路语义不同，别混用）：
 *   * `/key-pool/distribute/` —— 单向池：用**发送方**的 Kyber 公钥封装，
 *     发送方持有这批密钥用于向接收方发消息。服务端**写死 Kyber**，
 *     因为封装对象是发送方自己。
 *   * `/key-pool/generate/`   —— 节点间池：按 `algorithm` 分流，
 *     `kyber_kem` 用**接收方** Kyber 公钥、`falcon_lattice` 用**接收方** Falcon 公钥封装。
 *
 * 所以界面上要暴露 Falcon，就必须走这条 —— 只有它认 `algorithm` 参数
 * （2026-09-26 补：此前密钥池页只调 distribute，算法列永远只有 Kyber KEM）。
 */
export function generateNodePool(data) {
  return http.post('/key-pool/generate/', data).then(unwrap)
}

/** 检查并补充密钥池到目标规模 */
export function replenishKeyPool(data) {
  return http.post('/key-pool/replenish/', data).then(unwrap)
}

/** 清理过期密钥 */
export function cleanupKeyPool() {
  return http.post('/key-pool/cleanup/').then(unwrap)
}

/** 删除一条预分配密钥 */
export function deleteKeyPoolItem(id) {
  return http.delete(`/key-pool/${id}/`).then(unwrap)
}

/** 批量删除 */
export function batchDeleteKeyPool(ids) {
  return http.post('/key-pool/batch_delete/', { ids }).then(unwrap)
}

// ---------------------------------------------------------------- 会话密钥

/** 会话密钥列表 */
export function listSessions(params) {
  return http.get('/session-keys/', { params: { page: 1, limit: 500, ...(params || {}) } }).then(unwrapList)
}

// ---------------------------------------------------------------- 分发日志

/** 分发操作日志（节点密钥分发、公私钥上传等动作的流水） */
export function listDistributionLogs(params) {
  return http.get('/logs/', { params: { page: 1, limit: 500, ...(params || {}) } }).then(unwrapList)
}

// ---------------------------------------------------------------- 统计

/** 系统总览：节点数、会话数、消息数、最新区块 */
export function getOverviewStats() {
  return http.get('/stats/overview/').then(unwrap)
}

/** 分发模块自己那套链的统计（与 KMS 用的 FISCO 链不是一条，仅作参考） */
export function getDistributionChainStats() {
  return http.get('/stats/blockchain/').then(unwrap)
}