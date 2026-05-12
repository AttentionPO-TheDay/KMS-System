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

export function listGenerateKeys(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(apiBases.generateApi, `/generate/key/list${suffix}`)
}

export function listPublicGenerateKeys(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(apiBases.generateApi, `/generate/key/public-list${suffix}`)
}

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
