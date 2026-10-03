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
