import request from '@/utils/request'

export function listKeyDistributeRecord(query) {
  return request({
    url: '/distribute/record/list',
    method: 'get',
    params: query
  })
}

export function getKeyDistributeRecord(recordId) {
  return request({
    url: `/distribute/record/${recordId}`,
    method: 'get'
  })
}

export function addKeyDistributeRecord(data) {
  return request({
    url: '/distribute/record',
    method: 'post',
    data: data
  })
}

export function addKeyDistributeRecordBatch(data) {
  return request({
    url: '/distribute/record/batch',
    method: 'post',
    data: data
  })
}

export function updateKeyDistributeRecord(data) {
  return request({
    url: '/distribute/record',
    method: 'put',
    data: data
  })
}

export function delKeyDistributeRecord(recordId) {
  return request({
    url: `/distribute/record/${recordId}`,
    method: 'delete'
  })
}
