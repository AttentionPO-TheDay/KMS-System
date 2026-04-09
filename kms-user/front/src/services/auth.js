import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'
import { authState, clearSession, persistSession } from '@/services/session'

export { authState }

export async function fetchCaptcha() {
  return requestJson(apiBases.generateApi, '/captchaImage', { auth: false })
}

export async function login(credentials) {
  authState.loading = true
  authState.lastError = ''

  try {
    const loginData = await requestJson(apiBases.generateApi, '/login', {
      auth: false,
      method: 'POST',
      body: JSON.stringify(credentials)
    })

    authState.token = loginData.token || ''
    persistSession()
    await refreshProfile()
    return authState.profile
  } catch (error) {
    clearSession()
    authState.lastError = error.message
    throw error
  } finally {
    authState.loading = false
    authState.ready = true
  }
}

export async function refreshProfile() {
  if (!authState.token) {
    authState.profile = null
    authState.systemAccess.generate = { ok: false, message: '未登录' }
    authState.systemAccess.lifecycle = { ok: false, message: '未登录' }
    authState.systemAccess.distribute = { ok: false, message: '未登录' }
    authState.ready = true
    persistSession()
    return null
  }

  try {
    const [generateResult, lifecycleResult, distributeResult] = await Promise.allSettled([
      requestJson(apiBases.generateApi, '/getInfo'),
      requestJson(apiBases.lifecycleApi, '/getInfo'),
      requestJson(apiBases.distributeApi, '/getInfo')
    ])

    if (generateResult.status !== 'fulfilled') {
      throw generateResult.reason
    }

    authState.profile = generateResult.value?.user || null
    authState.systemAccess.generate = {
      ok: true,
      message: '已连接'
    }
    authState.systemAccess.lifecycle = lifecycleResult.status === 'fulfilled'
      ? { ok: true, message: '已连接' }
      : { ok: false, message: lifecycleResult.reason?.message || '访问失败' }
    authState.systemAccess.distribute = distributeResult.status === 'fulfilled'
      ? { ok: true, message: '已连接' }
      : { ok: false, message: distributeResult.reason?.message || '访问失败' }
    authState.lastError = ''
    persistSession()
    return authState.profile
  } catch (error) {
    authState.lastError = error.message
    throw error
  } finally {
    authState.ready = true
  }
}

export function logout() {
  clearSession()
  authState.lastError = ''
  authState.ready = true
}
