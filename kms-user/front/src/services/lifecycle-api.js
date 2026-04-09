import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

export function listLifecycleKeys(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(apiBases.lifecycleApi, `/lifecycle/keymanage/list${suffix}`)
}

export function getLifecycleKey(keyId) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/keymanage/${keyId}`)
}

export function updateLifecycleAutoUpdate(payload) {
  return requestJson(apiBases.lifecycleApi, '/lifecycle/keymanage/auto-update', {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export function updateLifecycleKey(payload) {
  return requestJson(apiBases.lifecycleApi, '/lifecycle/keymanage', {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export function revokeLifecycleKey(keyId) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/keymanage/${keyId}`, {
    method: 'DELETE'
  })
}
