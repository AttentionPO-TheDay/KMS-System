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

/**
 * 可申请的权限项。
 *
 * D1：用户侧 `PUBLIC_KEY_LIST`（查看公共密钥列表）已**整功能删除** ——
 * 该功能会让一个用户看到其他用户的公钥集合，与「密钥不外泄」的目标冲突。
 * 随之删除的还有：工作台的权限卡片项、生成页的「公钥列表」Tab、
 * 独立的「权限管理」页（申请入口改为「更新与回收」页的按钮 + 弹窗），
 * 以及生成域后端的整套权限申请接口（kms-generate）。
 *
 * 因此现在只剩 AUTO_UPDATE 一项，申请入口在「更新与回收」页。
 */
export const permissionFeatures = {
  AUTO_UPDATE: {
    system: 'lifecycle',
    label: '密钥自动更新',
    requestLevel: 0,
    apiBase: apiBases.lifecycleApi
  }
}

/** 取权限项元数据；未登记的 featureCode 直接抛错，避免出现 undefined.apiBase 这类隐晦失败 */
function requireFeature(featureCode) {
  const feature = permissionFeatures[featureCode]
  if (!feature) {
    throw new Error(`未登记的权限项: ${featureCode}`)
  }
  return feature
}

export function submitPermissionRequest(featureCode, payload) {
  const feature = requireFeature(featureCode)
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
  const feature = requireFeature(featureCode)
  const query = userId ? `?userId=${encodeURIComponent(userId)}` : ''
  return request(feature.apiBase, `/permission/request/list${query}`).then((payload) => {
    const filteredRows = (payload.rows || []).filter(r => r.featureCode === featureCode)
    return withFeatureMeta(featureCode, { ...payload, rows: filteredRows })
  })
}

export async function getLatestApprovedTemporaryRequest(featureCode, userId) {
  const payload = await listPermissionRequests(featureCode, userId)
  const rows = Array.isArray(payload?.rows) ? payload.rows : []

  return rows
    .filter((item) => String(item.status) === '1' && Number(item.isTemp) === 1)
    .sort((left, right) => getPermissionRequestTime(right) - getPermissionRequestTime(left))[0] || null
}

export function rollbackPermission(featureCode, requestId) {
  const feature = requireFeature(featureCode)
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
