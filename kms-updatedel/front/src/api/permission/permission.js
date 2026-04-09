import request from '@/utils/request'

// 提交权限申请
export function submitPermissionRequest(data) {
    return request({
        url: '/permission/request/submit',
        method: 'post',
        data: data
    })
}

// 查询权限申请列表
export function listPermissionRequests(query) {
    return request({
        url: '/permission/request/list',
        method: 'get',
        params: query
    })
}

// 获取权限申请详细信息
export function getPermissionRequest(requestId) {
    return request({
        url: '/permission/request/' + requestId,
        method: 'get'
    })
}

// 审批通过
export function approveRequest(requestId, data) {
    return request({
        url: '/permission/request/approve/' + requestId,
        method: 'put',
        data: data
    })
}

// 审批拒绝
export function rejectRequest(requestId, data) {
    return request({
        url: '/permission/request/reject/' + requestId,
        method: 'put',
        data: data
    })
}

// 回退权限
export function rollbackPermission(requestId) {
    return request({
        url: '/permission/request/rollback/' + requestId,
        method: 'put'
    })
}

// 删除权限申请
export function delPermissionRequest(requestId) {
    return request({
        url: '/permission/request/' + requestId,
        method: 'delete'
    })
}
