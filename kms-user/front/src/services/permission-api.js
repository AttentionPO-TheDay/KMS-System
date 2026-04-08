import { apiBases } from '@/config/api-bases'

async function request(base, path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  })
  const data = await response.json()
  if (!response.ok || data.code !== 200) {
    throw new Error(data.msg || '请求失败')
  }
  return data
}

export const permissionFeatures = {
  PUBLIC_KEY_LIST: {
    system: 'generate',
    label: '查看公共密钥列表',
    requestLevel: 1,
    apiBase: apiBases.generateApi
  },
  AUTO_UPDATE: {
    system: 'lifecycle',
    label: '密钥自动更新',
    requestLevel: 0,
    apiBase: apiBases.lifecycleApi
  }
}

export function submitPermissionRequest(featureCode, payload) {
  const feature = permissionFeatures[featureCode]
  return request(feature.apiBase, '/permission/request/submit', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      featureCode,
      systemCode: feature.system,
      featureName: feature.label,
      requestLevel: feature.requestLevel,
      isTemp: 1
    })
  })
}

export function listPermissionRequests(featureCode, userId) {
  const feature = permissionFeatures[featureCode]
  const query = userId ? `?userId=${encodeURIComponent(userId)}` : ''
  return request(feature.apiBase, `/permission/request/list${query}`)
}

export function rollbackPermission(featureCode, requestId) {
  const feature = permissionFeatures[featureCode]
  return request(feature.apiBase, `/permission/request/rollback/${requestId}`, {
    method: 'PUT'
  })
}
