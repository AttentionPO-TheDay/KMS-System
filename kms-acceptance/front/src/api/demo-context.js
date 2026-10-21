import { reactive, computed } from 'vue'

export const demoState = reactive({ context: null, available: false, stale: false, busy: false, message: '正在读取会话…' })
export const canRunAcceptance = computed(() => demoState.available && !demoState.stale && !demoState.busy && demoState.context?.principalType === 'ADMIN')
let bootstrapPromise = null
let performanceBusy = false
let securityBusy = false

export async function refreshDemoContext() {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const response = await fetch('/demo-api/lifecycle/demo/context', { credentials: 'same-origin', signal: controller.signal, cache: 'no-store' })
    const body = await response.json()
    const next = body.data
    if (!response.ok || body.code !== 200 || next?.entryMode !== 'DEMO' || next.enabled !== true || !Number.isSafeInteger(next.revision) || !next.csrfToken) {
      throw new Error('会话不可用，请从统一入口重新进入')
    }
    const old = demoState.context
    if (old && (old.revision !== next.revision || old.principalType !== next.principalType || old.csrfToken !== next.csrfToken)) {
      demoState.stale = true
      demoState.available = false
      demoState.message = '身份已改变，请刷新页面。'
      return
    }
    if (!old) demoState.context = Object.freeze({ ...next })
    demoState.available = !demoState.stale
    demoState.message = next.principalType === 'ADMIN' ? '' : '请在统一入口切换为管理员。'
  } catch (error) {
    demoState.available = false
    demoState.message = error.message || '会话不可用'
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

export function bootstrapDemoContext() {
  if (!bootstrapPromise) bootstrapPromise = refreshDemoContext().finally(() => { bootstrapPromise = null })
  return bootstrapPromise
}

// This is the only browser transport. Never forward identity/internal-token
// headers, never retry a stale request with the next role's revision.
export async function acceptanceFetch(url, options = {}) {
  const path = url.split('?')[0]
  const hasQuery = url.includes('?')
  const isLifecycle = /^\/acceptance\/lifecycle(?:\/run-[A-Za-z0-9-]+)?$/.test(path)
  if (!/^\/(health|scenarios|runs(?:\/run-[A-Za-z0-9-]+(?:\/cancel)?)?|security\/runs(?:\/run-[A-Za-z0-9-]+(?:\/cancel)?)?|proof\/runs|acceptance\/(criteria|evidence|lifecycle(?:\/run-[A-Za-z0-9-]+)?))$/.test(path) || (hasQuery && !isLifecycle)) throw new Error('未开放的验收端点')
  if (!demoState.context) await bootstrapDemoContext()
  if (!demoState.available || demoState.stale || demoState.context?.principalType !== 'ADMIN') throw new Error(demoState.message || '验收身份不可用')
  const mutation = options.method && options.method !== 'GET'
  if (mutation && !canRunAcceptance.value && !url.endsWith('/cancel')) throw new Error('任务正在执行或会话不可用')
  const headers = { 'Content-Type': 'application/json', 'X-Kms-Demo-Revision': String(demoState.context.revision) }
  if (mutation) headers['X-Kms-Demo-CSRF'] = demoState.context.csrfToken
  const wasBusy = demoState.busy
  if (mutation) demoState.busy = true
  let activeJob = false
  let completed = false
  try {
    const res = await fetch(`/acceptance-api${url}`, { ...options, credentials: 'same-origin', headers })
    const payload = await res.json()
    if (!res.ok) {
      if (res.status === 401 || (res.status === 409 && !String(payload.message).includes('BUSY'))) {
        demoState.stale = true
        demoState.available = false
        demoState.message = '演示会话失效或版本已改变，请刷新入口。'
      }
      throw new Error(payload.message || payload.error || 'Request Failed')
    }
    completed = true
    activeJob = res.status === 202 && ['running', 'preparing'].includes(payload.status)
    if (!mutation && url === '/runs') {
      performanceBusy = (payload.data || []).some(run => ['running', 'preparing'].includes(run.status))
      demoState.busy = performanceBusy || securityBusy
    }
    if (!mutation && url === '/security/runs') {
      securityBusy = (payload.data || []).some(run => ['running', 'preparing'].includes(run.status))
      demoState.busy = performanceBusy || securityBusy
    }
    return payload
  } finally {
    if (mutation) demoState.busy = activeJob || (!completed && wasBusy)
  }
}
