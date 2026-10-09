import axios from 'axios'
import { IS_DEMO, documentURL, entryPath, setEntryPrincipal } from './entry-mode'

const authority = axios.create({ baseURL: '/demo-api/lifecycle/demo/context', withCredentials: true, timeout: 15000 })
let context = null
let loading = null
let transitioning = false
let controller = new AbortController()

export function getDemoContext() { return context }

function acceptContext(body) {
  if (body?.code !== 200 || !body?.data || body.data.entryMode !== 'DEMO' || body.data.enabled !== true ||
      !['NODE', 'ADMIN', null].includes(body.data.principalType)) {
    throw new Error(body?.msg || '受控演示未启用，或演示会话不可用')
  }
  context = Object.freeze({ ...body.data })
  setEntryPrincipal(context.principalType)
  return context
}

export function loadDemoContext(force = false) {
  if (!IS_DEMO) return Promise.reject(new Error('独立运行入口不能使用演示会话'))
  if (context && !force) return Promise.resolve(context)
  if (!loading) {
    loading = authority.get('').then(res => acceptContext(res.data)).finally(() => { loading = null })
  }
  return loading
}

export function demoHeaders() {
  if (transitioning) throw new Error('演示视角正在切换，请等待页面重新载入')
  if (!context?.principalType || !context.csrfToken || !Number.isInteger(context.revision)) {
    throw new Error('演示会话尚未就绪，请从演示入口重新进入')
  }
  return { 'X-Kms-Demo-CSRF': context.csrfToken, 'X-Kms-Demo-Revision': String(context.revision) }
}

/** Dispatch captures the current revision; never replay an old request with a new role. */
export function applyDemoRequest(config, kind = 'lifecycle') {
  if (!IS_DEMO) return config
  const base = String(config.baseURL || '')
  if (base.includes('generate')) kind = 'generate'
  else if (base.includes('pqkds')) kind = 'pqkds'
  if (/^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(config.url || '')) throw new Error('演示请求只能访问当前受控网关')
  config.baseURL = `/demo-api/${kind}`
  for (const name of Object.keys(config.headers || {})) {
    if (name.toLowerCase() === 'authorization') delete config.headers[name]
  }
  Object.assign(config.headers, demoHeaders())
  config.withCredentials = true
  config.signal = controller.signal
  return config
}

async function boundary(action, data, destination) {
  if (transitioning) return
  transitioning = true
  controller.abort()
  try {
    // Mutations need the old role's CSRF/revision while business dispatch is stopped.
    const headers = context?.csrfToken && Number.isInteger(context.revision)
      ? { 'X-Kms-Demo-CSRF': context.csrfToken, 'X-Kms-Demo-Revision': String(context.revision) }
      : {}
    const res = await authority.post(`/${action}`, data || {}, { headers })
    const next = acceptContext(res.data)
    globalThis.location.replace(documentURL(destination(next)))
  } catch (error) {
    // An invalid node switch may issue a cookie and advance an anonymous revision.
    // Re-read authority state before allowing the explicit admin/retry action; keep the error visible.
    try { await loadDemoContext(true) } catch { context = null; setEntryPrincipal(null) }
    transitioning = false
    controller = new AbortController()
    const message = error?.response?.data?.msg || error.message || '演示视角切换失败'
    const stale = error?.response?.status === 409 || error?.response?.data?.code === 409 || /DEMO_REVISION/.test(message)
    throw new Error(stale ? '演示视角已在其他页面改变，请刷新当前页面后再操作。不会回退为独立运行身份。' : message)
  }
}

export async function enterDemo(nodeId) {
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(nodeId || '')) throw new Error('节点 ID 必须是 1–64 位 ASCII 字母、数字、点、下划线或连字符')
  return boundary('entry', { nodeId }, next => next.node?.status === 'PENDING_INIT'
    ? '/demo/node/initialize' : entryPath('/workbench', 'NODE'))
}

export function switchDemo(role) {
  if (role !== 'ADMIN' && role !== 'NODE') return Promise.reject(new Error('未知演示视角'))
  return boundary(role === 'ADMIN' ? 'admin' : 'node', {}, next => role === 'ADMIN'
    ? entryPath('/index', 'ADMIN') : (next.node?.status === 'PENDING_INIT' ? '/demo/node/initialize' : entryPath('/workbench', 'NODE')))
}

export async function logoutDemo() {
  // Logout returns an anonymous context on current implementations; no business role is retained.
  const headers = demoHeaders()
  transitioning = true
  controller.abort()
  try {
    await authority.post('/logout', {}, { headers })
    context = null
    globalThis.location.replace(documentURL('/demo'))
  } catch (error) {
    transitioning = false
    controller = new AbortController()
    throw error
  }
}
