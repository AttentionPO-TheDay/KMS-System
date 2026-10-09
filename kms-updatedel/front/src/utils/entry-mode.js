// The namespace is fixed for the lifetime of this document, including pending IDB work.
const documentPath = globalThis.location?.pathname || ''
const basePath = (import.meta.env?.BASE_URL || '/updatedel/').replace(/\/$/, '')
const applicationPath = basePath && (documentPath === basePath || documentPath.startsWith(`${basePath}/`))
  ? documentPath.slice(basePath.length) : documentPath
export const IS_DEMO = /^\/demo(?:\/|$)/.test(applicationPath)
export const ENTRY_MODE = IS_DEMO ? 'DEMO' : 'STANDALONE'
export const KEYSTORE_DB_NAME = IS_DEMO ? 'kms-demo-node-keystore' : 'kms-node-keystore'

let principal = null
export function setEntryPrincipal(value) {
  principal = value === 'ADMIN' || value === 'NODE' ? value : null
}

export function originalPath(path = '') {
  return String(path).replace(/^\/demo\/(?:node|admin)(?=\/|$)/, '') || '/'
}

/** Shared business navigation is namespaced, never interpreted as a role switch. */
export function entryPath(path, principalType = principal) {
  if (!IS_DEMO || !path || /^(?:https?:|\/demo(?:\/|$))/.test(path)) return path
  if (path === '/node-init') return '/demo/node/initialize'
  if (path === '/login') return '/demo'
  const role = principalType === 'ADMIN' ? 'admin' : 'node'
  return `/demo/${role}${String(path).startsWith('/') ? path : `/${path}`}`
}

export function documentURL(path) {
  const base = import.meta.env?.BASE_URL || '/updatedel/'
  return `${base.replace(/\/?$/, '/')}${String(path).replace(/^\//, '')}`
}

export function namespaceRoutes(routes, principalType) {
  if (!IS_DEMO) return routes
  const prefix = `/demo/${principalType === 'ADMIN' ? 'admin' : 'node'}`
  function visit(route, top = false) {
    const copy = { ...route, meta: { ...(route.meta || {}) } }
    if (top || String(copy.path).startsWith('/')) copy.path = `${prefix}${copy.path === '/' || copy.path === '' ? '' : copy.path}`
    if (copy.name) copy.name = `Demo${principalType}_${copy.name}`
    if (typeof copy.redirect === 'string' && copy.redirect.startsWith('/')) copy.redirect = entryPath(copy.redirect, principalType)
    if (copy.meta.activeMenu) copy.meta.activeMenu = entryPath(copy.meta.activeMenu, principalType)
    if (copy.children) copy.children = copy.children.map(child => visit(child))
    return copy
  }
  return routes.map(route => visit(route, true))
}
