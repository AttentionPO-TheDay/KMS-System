import request from '@/utils/request'

export function listPermissionRequests(query) {
  return request({
    url: '/permission/request/list',
    method: 'get',
    params: query
  })
}

export function approveRequest(requestId, data) {
  return request({
    url: '/permission/request/approve/' + requestId,
    method: 'put',
    data
  })
}

export function rejectRequest(requestId, data) {
  return request({
    url: '/permission/request/reject/' + requestId,
    method: 'put',
    data
  })
}
