import request from '@/utils/request'

// 查询密钥管理列表
export function listKeymanage(query) {
  return request({
    url: '/lifecycle/keymanage/list',
    method: 'get',
    params: query
  })
}

// 查询密钥管理详细
export function getKeymanage(keyId) {
  return request({
    url: '/lifecycle/keymanage/' + keyId,
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
  })
}

// 修改密钥管理
export function updateKeymanage(data) {
  return request({
    url: '/lifecycle/keymanage',
    method: 'put',
    data: data
  })
}

// 删除密钥管理
export function delKeymanage(keyId) {
  return request({
    url: '/lifecycle/keymanage/' + keyId,
    method: 'delete'
  })
}
