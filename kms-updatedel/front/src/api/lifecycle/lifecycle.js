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

// 获取公共参数
export function getComParam(data) {
  return request({
    url: '/lifecycle/keymanage/comparam',
    method: 'post',
    data: data
  })
}

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
