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

/**
 * 「公钥查询」：查看全部用户的公钥资产。
 *
 * 原先打的是 `/generate/key/public-list` —— 那是用户侧「查看公共密钥列表」的接口，
 * 已随 D1 整体删除（它让任何被授权的用户都能读到别人的公钥集合）。
 * 现改用 `/generate/key/public-assets`：仅管理员可访问，且服务端只回填公钥材料，
 * 私钥分片（SM2 的 partialKey、SSCL 的 SSCLEA）与格算法的完整私钥都不会出库。
 *
 * 注意：本应用的 axios 实例已由 VITE_APP_BASE_API（= /generate-api）提供 baseURL，
 * 因此这里保持相对路径即可，无需再显式传 baseURL。
 */
export function listQueryPublicKeys(query) {
  return request({
    url: '/generate/key/public-assets',
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
