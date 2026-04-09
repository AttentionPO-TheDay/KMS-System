import request from '@/utils/request'

function normalizeTable(res) {
  return {
    ...res,
    rows: res.rows || res.data || [],
    total: res.total || ((res.data || []).length)
  }
}

export function listQueryKeys(query) {
  return request({
    url: '/generate/key/list',
    method: 'get',
    params: query
  }).then(normalizeTable)
}

export function listQueryPublicKeys(query) {
  return request({
    url: '/generate/key/public-list',
    method: 'get',
    params: query
  }).then(normalizeTable)
}

export function getKeyChainStatus(keyId) {
  return request({
    url: `/generate/key/chain/${keyId}`,
    method: 'get'
  }).then(res => res.data || res)
}

export function listBusinessUsers() {
  return request({
    url: '/generate/user/non-admin-list',
    method: 'get'
  }).then(res => res.data || [])
}
