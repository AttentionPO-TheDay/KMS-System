import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

const lifecycleFieldMap = {
  keyId: 'key_id',
  userId: 'user_id',
  userName: 'user_name',
  ua: 'ua',
  encrytType: 'encryt_type',
  encrytName: 'encryt_name',
  keyName: 'key_name',
  keyUse: 'key_use',
  keyValue: 'key_value',
  creTime: 'cre_time',
  updTime: 'upd_time',
  autoUpdate: 'auto_update',
  status: 'status',
  version: 'version',
  chainHash: 'chain_hash',
  blockHeight: 'block_height',
  chainStatus: 'chain_status',
  keyDomain: 'key_domain'
}

function hasOwn(payload, key) {
  return Object.prototype.hasOwnProperty.call(payload, key)
}

function normalizeLifecycleKey(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return raw
  }

  return {
    ...raw,
    keyId: raw.keyId ?? raw.key_id ?? null,
    userId: raw.userId ?? raw.user_id ?? null,
    userName: raw.userName ?? raw.user_name ?? '',
    ua: raw.ua ?? '',
    encrytType: raw.encrytType ?? raw.encryt_type ?? '',
    encrytName: raw.encrytName ?? raw.encryt_name ?? '',
    keyName: raw.keyName ?? raw.key_name ?? '',
    keyUse: raw.keyUse ?? raw.key_use ?? '',
    keyValue: raw.keyValue ?? raw.key_value ?? '',
    creTime: raw.creTime ?? raw.cre_time ?? '',
    updTime: raw.updTime ?? raw.upd_time ?? '',
    autoUpdate: raw.autoUpdate ?? raw.auto_update ?? '',
    status: raw.status ?? '',
    version: raw.version ?? null,
    chainHash: raw.chainHash ?? raw.chain_hash ?? '',
    blockHeight: raw.blockHeight ?? raw.block_height ?? null,
    chainStatus: raw.chainStatus ?? raw.chain_status ?? '',
    keyDomain: raw.keyDomain ?? raw.key_domain ?? ''
  }
}

function serializeLifecycleKey(payload = {}) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return payload
  }

  const serialized = {}
  Object.entries(lifecycleFieldMap).forEach(([camelKey, snakeKey]) => {
    if (hasOwn(payload, camelKey)) {
      serialized[snakeKey] = payload[camelKey]
    }
  })
  return serialized
}

function normalizeLifecycleResponse(response) {
  if (!response || typeof response !== 'object' || Array.isArray(response)) {
    return response
  }

  return {
    ...response,
    data: response.data && typeof response.data === 'object' && !Array.isArray(response.data)
      ? normalizeLifecycleKey(response.data)
      : response.data,
    rows: Array.isArray(response.rows)
      ? response.rows.map(normalizeLifecycleKey)
      : response.rows
  }
}

export function listLifecycleKeys(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(apiBases.lifecycleApi, `/lifecycle/keymanage/list${suffix}`).then(normalizeLifecycleResponse)
}

export function getLifecycleKey(keyId) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/keymanage/${keyId}`).then(normalizeLifecycleResponse)
}

export function updateLifecycleAutoUpdate(payload) {
  return requestJson(apiBases.lifecycleApi, '/lifecycle/keymanage/auto-update', {
    method: 'PUT',
    body: serializeLifecycleKey(payload)
  }).then(normalizeLifecycleResponse)
}

export function updateLifecycleKey(payload) {
  return requestJson(apiBases.lifecycleApi, '/lifecycle/keymanage', {
    method: 'PUT',
    body: serializeLifecycleKey(payload)
  }).then(normalizeLifecycleResponse)
}

export function revokeLifecycleKey(keyId) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/keymanage/${keyId}`, {
    method: 'DELETE'
  })
}

export function listLifecycleOperationRecords(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(apiBases.lifecycleApi, `/lifecycle/operation-record/list${suffix}`)
}

export function receiveLifecycleOperationRecord(recordId) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/operation-record/receive/${recordId}`, {
    method: 'PUT'
  })
}
