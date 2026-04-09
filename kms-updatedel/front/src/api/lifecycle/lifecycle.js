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

// 修改密钥管理
export function updateKeymanage(data) {
  return request({
    url: '/lifecycle/keymanage',
    method: 'put',
    data: data
  })
}

// 修改密钥自动更新状态
export function updateKeyAutoUpdate(data) {
  return request({
    url: '/lifecycle/keymanage/auto-update',
    method: 'put',
    data: data
  })
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
