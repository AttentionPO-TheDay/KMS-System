import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

async function request(base, path, options = {}) {
  return requestJson(base, path, options)
}

function withFeatureMeta(featureCode, payload) {
  const feature = permissionFeatures[featureCode]
  if (!payload || !feature) {
    return payload
  }

  const rows = (payload.rows || []).map((row) => ({
    featureCode,
    systemCode: feature.system,
    featureName: feature.label,
    ...row
  }))

  return {
    ...payload,
    featureCode,
    systemCode: feature.system,
    featureName: feature.label,
    rows
  }
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
  return request(feature.apiBase, `/permission/request/list${query}`).then((payload) => withFeatureMeta(featureCode, payload))
}

export async function getLatestApprovedTemporaryRequest(featureCode, userId) {
  const payload = await listPermissionRequests(featureCode, userId)
  const rows = Array.isArray(payload?.rows) ? payload.rows : []

  return rows
    .filter((item) => String(item.status) === '1' && Number(item.isTemp) === 1)
    .sort((left, right) => getPermissionRequestTime(right) - getPermissionRequestTime(left))[0] || null
}

export function rollbackPermission(featureCode, requestId) {
  const feature = permissionFeatures[featureCode]
  return request(feature.apiBase, `/permission/request/rollback/${requestId}`, {
    method: 'PUT'
  })
}

function getPermissionRequestTime(item) {
  const value = item?.approveTime || item?.requestTime
  const parsed = value ? new Date(value).getTime() : NaN
  if (!Number.isNaN(parsed)) {
    return parsed
  }
  return Number(item?.requestId) || 0
}
