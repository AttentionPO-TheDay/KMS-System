import request from '@/utils/request'

/*
 * 生成域（generate-java，端口 9081）的接口封装。
 *
 * 重要：本文件所有请求**必须显式指定 baseURL**。
 * 管理端合并后，应用的默认 baseURL 是 `/lifecycle-api`（指向 updatedel-java 9082），
 * 若不指定，生成域的请求会被错误地打到生命周期服务上。
 *
 * 本文件由两个应用的版本合并而成：
 *   - addGenerateKeymanage / getGenerateComParam —— 原本只在 updatedel 侧存在，
 *     供生命周期页面调用生成域，继续保留原名以免破坏既有引用。
 *   - 其余函数 —— 原本只在 generate 侧存在，供生成域页面使用。
 * 两边的导出名不冲突，因此直接合并到一个模块。
 */

const generateBaseURL = import.meta.env.VITE_APP_GENERATE_API || '/generate-api'

// ---------- 密钥列表与详情 ----------

// 查询密钥管理列表
export function listKeymanage(query) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/key/list',
    method: 'get',
    params: query
  }).then(res => ({
    ...res,
    rows: res.rows || res.data || [],
    total: res.total || ((res.data || []).length)
  }))
}

// 查询密钥管理详细
export function getKeymanage(keyId) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/key/' + keyId,
    method: 'get'
  })
}

// ---------- 公共参数 ----------

// 获取公共参数（生成域页面使用）
export function getComParam(data) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/keymanage/comparam',
    method: 'post',
    data: data
  }).then(res => res.data || res)
}

// 获取公共参数（生命周期域页面使用，语义与 getComParam 相同，保留原名以兼容既有引用）
export function getGenerateComParam(data) {
  return getComParam(data)
}

// ---------- 密钥生成与变更 ----------

// 新增密钥管理（生成域页面使用）
export function addKeymanage(data) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/keymanage',
    method: 'post',
    data: data
  })
}

// 新增密钥管理（生命周期域页面使用，保留原名以兼容既有引用）
export function addGenerateKeymanage(data) {
  return addKeymanage(data)
}

// 修改密钥管理
export function updateKeymanage(data) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/keymanage',
    method: 'put',
    data: data
  })
}

// 删除密钥管理
export function delKeymanage(keyId) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/keymanage/' + keyId,
    method: 'delete'
  })
}

// ---------- 历史记录与看板 ----------

export function addHistoryRecord(data) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/key/history/manual',
    method: 'post',
    data: data
  })
}

export function getDashboardSummary() {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/key/dashboard/summary',
    method: 'get'
  }).then(res => res.data || res)
}