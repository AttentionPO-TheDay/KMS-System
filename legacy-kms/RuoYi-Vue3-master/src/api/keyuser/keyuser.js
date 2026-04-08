import request from '@/utils/request'

// 查询用户管理列表
export function listKeyuser(query) {
  return request({
    url: '/keyuser/keyuser/list',
    method: 'get',
    params: query
  })
}

// 查询用户管理详细
export function getKeyuser(userId) {
  return request({
    url: '/keyuser/keyuser/' + userId,
    method: 'get'
  })
}

// 新增用户管理
export function addKeyuser(data) {
  return request({
    url: '/keyuser/keyuser',
    method: 'post',
    data: data
  })
}

// 修改用户管理
export function updateKeyuser(data) {
  return request({
    url: '/keyuser/keyuser',
    method: 'put',
    data: data
  })
}

// 删除用户管理
export function delKeyuser(userId) {
  return request({
    url: '/keyuser/keyuser/' + userId,
    method: 'delete'
  })
}
