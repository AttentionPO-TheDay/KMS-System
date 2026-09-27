import request from '@/utils/request'

// 查询密钥管理列表
export function listKeymanage(query) {
  return request({
    url: '/generate/key/list',
    method: 'get',
    params: query
  }).then(res => ({
    ...res,
    rows: res.rows || res.data || [],
    total: res.total || ((res.data || []).length)
  }))
}

// 原「公共密钥列表」接口封装已删除：它打的是用户侧「查看公共密钥列表」的接口，
// 已随 D1 整体删除（该接口让任何被授权的用户都能读到别人的公钥集合）。
// 公钥资产现只经 /generate/key/public-assets 暴露（仅管理员），见 api/query/keyQuery.js。

// 查询密钥管理详细
export function getKeymanage(keyId) {
  return request({
    url: '/generate/key/' + keyId,
    method: 'get'
  })
}

// 获取公共参数
export function getComParam(data) {
  return request({
    url: '/generate/keymanage/comparam',
    method: 'post',
    data: data
  }).then(res => res.data || res)
}

// 新增密钥管理
export function addKeymanage(data) {
  return request({
    url: '/generate/keymanage',
    method: 'post',
    data: data
  })
}

export function addHistoryRecord(data) {
  return request({
    url: '/generate/key/history/manual',
    method: 'post',
    data: data
  })
}

export function getDashboardSummary() {
  return request({
    url: '/generate/key/dashboard/summary',
    method: 'get'
  }).then(res => res.data || res)
}

// 修改密钥管理
export function updateKeymanage(data) {
  return request({
    url: '/generate/keymanage',
    method: 'put',
    data: data
  })
}

// 删除密钥管理
export function delKeymanage(keyId) {
  return request({
    url: '/generate/keymanage/' + keyId,
    method: 'delete'
  })
}
