import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

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

export function getGenerateKey(keyId) {
  return requestJson(apiBases.generateApi, `/generate/key/${keyId}`)
}

export async function getCommonParams(payload) {
  const data = await requestJson(apiBases.generateApi, '/generate/keymanage/comparam', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
  return data?.data || data
}
