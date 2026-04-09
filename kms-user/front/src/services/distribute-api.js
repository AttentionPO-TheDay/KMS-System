import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

export function listDistributeRecords(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(apiBases.distributeApi, `/distribute/record/list${suffix}`)
}

export function getDistributeRecord(recordId) {
  return requestJson(apiBases.distributeApi, `/distribute/record/${recordId}`)
}
