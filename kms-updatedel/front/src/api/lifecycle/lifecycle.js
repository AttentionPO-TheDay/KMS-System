import request from '@/utils/request'

function normalizeKeymanage(record) {
  if (!record || typeof record !== 'object' || Array.isArray(record)) {
    return record
  }

  return {
    ...record,
    keyId: record.keyId ?? record.key_id ?? null,
    userId: record.userId ?? record.user_id ?? null,
    userName: record.userName ?? record.user_name ?? '',
    ua: record.ua ?? '',
    encrytType: record.encrytType ?? record.encryt_type ?? '',
    encrytName: record.encrytName ?? record.encryt_name ?? '',
    keyName: record.keyName ?? record.key_name ?? '',
    keyUse: record.keyUse ?? record.key_use ?? '',
    keyValue: record.keyValue ?? record.key_value ?? '',
    creTime: record.creTime ?? record.cre_time ?? '',
    updTime: record.updTime ?? record.upd_time ?? '',
    autoUpdate: record.autoUpdate ?? record.auto_update ?? '',
    status: record.status ?? '',
    version: record.version ?? null,
    chainHash: record.chainHash ?? record.chain_hash ?? '',
    blockHeight: record.blockHeight ?? record.block_height ?? null,
    chainStatus: record.chainStatus ?? record.chain_status ?? '',
    keyDomain: record.keyDomain ?? record.key_domain ?? ''
  }
}

function normalizeKeymanageResponse(response) {
  if (!response || typeof response !== 'object' || Array.isArray(response)) {
    return response
  }

  return {
    ...response,
    data: response.data && typeof response.data === 'object' && !Array.isArray(response.data)
      ? normalizeKeymanage(response.data)
      : response.data,
    rows: Array.isArray(response.rows)
      ? response.rows.map(normalizeKeymanage)
      : response.rows
  }
}

// 查询密钥管理列表
export function listKeymanage(query) {
  return request({
    url: '/lifecycle/keymanage/list',
    method: 'get',
    params: query
  }).then(normalizeKeymanageResponse)
}

// 查询密钥管理详细
export function getKeymanage(keyId) {
  return request({
    url: '/lifecycle/keymanage/' + keyId,
    method: 'get'
  }).then(normalizeKeymanageResponse)
}

// 密钥关联分析
export function getKeymanageAnalysis(keyId) {
  return request({
    url: '/lifecycle/keymanage/analysis/' + keyId,
    method: 'get'
  })
}

/**
 * KMS-014（计划 §7 阶段 6）：以**节点长期密钥**为线索的泄漏分析。
 *
 * 与 `getKeymanageAnalysis` 是两个**不同的标识空间**：那个收 kms.keymanage
 * 的数字 keyId（用户密钥），这里收分发模块 NodeLongTermKey 的字符串 keyId。
 * KMS-008 之后的节点到节点分发完全不用用户密钥，处置节点密钥泄漏走这条。
 * `version` 可选 —— 不给表示该 keyId 的**全部版本**。
 */
export function getNodeKeyAnalysis(longTermKeyId, version) {
  return request({
    url: '/lifecycle/keymanage/node-key-analysis/' + encodeURIComponent(longTermKeyId),
    method: 'get',
    params: version ? { version } : undefined
  })
}

/**
 * 阶段 4（文档 §5.2）：某逻辑密钥的历史版本列表。
 *
 * 返回**不含当前版本** —— 当前版本在 keymanage 表里（走 getKeymanage），
 * 历史快照在版本历史表里。要看完整版本序列，需把两者拼起来。
 */
export function getKeyVersionHistory(keyId) {
  return request({
    url: '/lifecycle/keymanage/' + keyId + '/versions',
    method: 'get'
  })
}

/**
 * 阶段 7（文档 §8.1 + §8.2）：单把密钥的健康检查。
 *
 * 返回 { health, findings[], observations[] }：
 *   health       OK / SUSPICIOUS / REVOKED
 *   findings     命中的规则，每条带 rule/severity/message/advice
 *   observations 原始观测值，供人工核对（不参与判定）
 */
export function getKeyHealth(keyId) {
  return request({
    url: '/lifecycle/keymanage/health/' + keyId,
    method: 'get'
  })
}

// 说明：原此处有 getComParam()，POST /lifecycle/keymanage/comparam。
// 该端点从未在 kms-updatedel/java-backend 中实现（已核对全部 controller），
// 且全仓库无任何调用方，属死契约，故移除。
// 公共参数应由生成系统提供：POST /generate/keymanage/comparam。

// 新增密钥管理
export function addKeymanage(data) {
  return request({
    url: '/lifecycle/keymanage',
    method: 'post',
    data: data
  }).then(normalizeKeymanageResponse)
}

// 修改密钥管理
export function updateKeymanage(data) {
  return request({
    url: '/lifecycle/keymanage',
    method: 'put',
    data: data
  }).then(normalizeKeymanageResponse)
}

// 修改密钥自动更新状态
export function updateKeyAutoUpdate(data) {
  return request({
    url: '/lifecycle/keymanage/auto-update',
    method: 'put',
    data: data
  }).then(normalizeKeymanageResponse)
}

export function getDashboardSummary() {
  return request({
    url: '/lifecycle/keymanage/dashboard/summary',
    method: 'get'
  }).then(res => res.data || res)
}

// 删除密钥管理
export function delKeymanage(keyId) {
  return request({
    url: '/lifecycle/keymanage/' + keyId,
    method: 'delete'
  })
}

// ===========================================================================
// KMS-019：自动更新任务记录（轮次 + 逐密钥明细）
// ---------------------------------------------------------------------------
// 与上面的 updateKeyAutoUpdate（逐密钥开关注入）是两条不同的路：
//   * `/lifecycle/keymanage/auto-update` —— 改**一把**密钥的开关（PUT，已是既有接口）；
//   * `/lifecycle/auto-update/*`         —— 看**任务跑了没有**（只读 + 管理员手动补跑）。
// 后端刻意把它们分在两个前缀下（AutoUpdateRunController 类注释），前端同样分开，
// 免得日后把"任务轮次"错接到"开关"的响应形状上。
// ===========================================================================

/** 轮次列表（倒序；非管理员只看到影响过自己密钥的轮次，由后端收敛）。 */
export function listAutoUpdateRuns(query) {
  return request({
    url: '/lifecycle/auto-update/runs',
    method: 'get',
    params: query
  })
}

/** 单轮明细（分页；runId 在路径上，keyId/result 可选筛选）。 */
export function listAutoUpdateRunItems(runId, query) {
  return request({
    url: '/lifecycle/auto-update/runs/' + encodeURIComponent(runId),
    method: 'get',
    params: query
  })
}

/**
 * 管理员手动触发一轮（与定时任务同一个 service 方法，会**真的轮换**候选密钥）。
 * 仅平台管理员 —— 普通用户的即时更新走「密钥更新」页。
 */
export function triggerAutoUpdateRunOnce() {
  return request({
    url: '/lifecycle/auto-update/run-once',
    method: 'post',
    // 批量轮换同步执行，不沿用普通查询的 10 秒超时。
    timeout: 120000
  })
}

/**
 * 每把密钥的最近一条执行结果（keyautoupdate 页「上次执行」列）。
 * 一次带当前页的 keyIds（逗号分隔），避免每行一个请求的 N+1。
 */
export function listLatestAutoUpdateItems(keyIds) {
  return request({
    url: '/lifecycle/auto-update/latest',
    method: 'get',
    params: { keyIds: (keyIds || []).join(',') }
  })
}

// ===========================================================================
// KMS-022：批量一致性检查（用户密钥侧）
// ---------------------------------------------------------------------------
// 与上面的 getKeyHealth（单钥检查）同源（后端复用同一套规则），差别只在
// 粒度：单钥是"这一把怎么样"，这里是"这一批扫了哪些、结论各是什么"，
// 结果落库可回看（key_health_scan_run / item）。
//
// 节点长期密钥侧**不走这里**：它的健康由 Python 侧巡检负责，页面只读展示，
// 用 @/api/pqkds/node-self 的 listNodeKeyReviews（见 keyHealth 页的说明）。
// ===========================================================================

/**
 * 触发一轮扫描。
 * 管理员可不传 userId（全量）或指定某个用户；普通用户无论传什么都只扫自己
 * （传了别人的会被明确拒绝，不是静默改写）。
 */
export function triggerKeyHealthScan(userId) {
  return request({
    url: '/lifecycle/keymanage/health/scan',
    method: 'post',
    params: userId ? { userId } : undefined,
    // 扫描逐钥复用健康规则，批量请求允许更长的处理时间。
    timeout: 120000
  })
}

/** 扫描批次列表（倒序；非管理员只看到属于自己或扫过自己密钥的批次）。 */
export function listKeyHealthScans(query) {
  return request({
    url: '/lifecycle/keymanage/health/scans',
    method: 'get',
    params: query
  })
}

/** 单批明细（分页；verdict / keyId 可选筛选）。 */
export function listKeyHealthScanItems(runId, query) {
  return request({
    url: '/lifecycle/keymanage/health/scans/' + encodeURIComponent(runId),
    method: 'get',
    params: query
  })
}
