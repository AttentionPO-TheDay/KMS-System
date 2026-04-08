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
    url: '/generate/request/comparam',
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
