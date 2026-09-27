import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

const generateFieldMap = {
  operatorMetadata: 'operator_metadata',
  pqMode: 'pq_mode'
}

function hasOwn(payload, key) {
  return Object.prototype.hasOwnProperty.call(payload, key)
}

function serializeGenerateKey(payload = {}) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return payload
  }

  const serialized = { ...payload }
  Object.entries(generateFieldMap).forEach(([camelKey, snakeKey]) => {
    if (hasOwn(payload, camelKey)) {
      serialized[snakeKey] = payload[camelKey]
      delete serialized[camelKey]
    }
  })
  return serialized
}

export function batchGetGenerateChainStatus(keyIds = []) {
  const normalizedKeyIds = [...new Set(keyIds.map((item) => Number(item)).filter((item) => Number.isFinite(item) && item > 0))]
  if (!normalizedKeyIds.length) {
    return Promise.resolve({})
  }

  return requestJson(apiBases.generateApi, '/generate/key/chain/batch', {
    method: 'POST',
    body: JSON.stringify({ keyIds: normalizedKeyIds })
  }).then((payload) => payload?.data || {})
}

function buildQuerySuffix(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  return search.toString() ? `?${search.toString()}` : ''
}

export function listGenerateKeys(query = {}) {
  return requestJson(apiBases.generateApi, `/generate/key/list${buildQuerySuffix(query)}`)
}

// listPublicGenerateKeys / `/generate/key/public-list` 已按 D1 删除：
// 该接口是「查看公共密钥列表」功能的后端入口，会让一个用户读到其他用户的公钥集合。
// 对应的权限项 PUBLIC_KEY_LIST 也一并从 permission-api.js 与生成域后端移除。

export function getGenerateKey(keyId) {
  return requestJson(apiBases.generateApi, `/generate/key/${keyId}`)
}

export function createGenerateKey(payload) {
  return requestJson(apiBases.generateApi, '/generate/keymanage', {
    method: 'POST',
    body: JSON.stringify(serializeGenerateKey(payload))
  })
}

export async function getCommonParams(payload) {
  const data = await requestJson(apiBases.generateApi, '/generate/keymanage/comparam', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
  return data?.data || data
}
