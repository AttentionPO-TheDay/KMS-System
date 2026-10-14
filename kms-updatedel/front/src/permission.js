import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { isHttp } from '@/utils/validate'
import useUserStore from '@/store/modules/user'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import { landingPath } from '@/utils/landing'
import { entryPath, originalPath } from '@/utils/entry-mode'
import { loadDemoContext } from '@/utils/demo-context'
import { canEnterNodeWorkspace } from '@/utils/node-workspace-access'

NProgress.configure({ showSpinner: false })

function registerDynamicRoutes() {
  return usePermissionStore().generateRoutes().then(accessRoutes => {
    accessRoutes.forEach(route => {
      if (!isHttp(route.path)) router.addRoute(route)
    })
    return accessRoutes
  })
}

let demoWorkspaceReady = false

router.beforeEach(async (to, from, next) => {
  NProgress.start()
  // Retired ordinary/standalone links never bootstrap a token-based document.
  if (to.path !== '/demo' && to.path !== '/401' && !to.path.startsWith('/demo/')) {
    next({ path: '/demo', replace: true })
    NProgress.done()
    return
  }
  if (to.path === '/demo' || to.path === '/401') {
    next()
    NProgress.done()
    return
  }
  try {
    const context = await loadDemoContext()
    if (!context.principalType) {
      next({ path: '/demo', query: { reason: '请先解析已有节点，或进入管理控制台。' }, replace: true })
      return
    }
    const principal = context.principalType
    // A URL is navigation intent only. It never changes the authority's role.
    const canonical = to.path === '/demo/node/initialize' && principal === 'NODE'
      ? to.path : entryPath(originalPath(to.path), principal)
    if (canonical !== to.path) {
      next({ path: canonical, query: to.query, hash: to.hash, replace: true })
      return
    }
    const userStore = useUserStore()
    if (!userStore.roles.length) await userStore.getInfo()
    if (principal === 'NODE') {
      if (to.path === '/demo/node/initialize') { demoWorkspaceReady = false; next(); return }
      if (!demoWorkspaceReady) {
        const { inspectInitialization } = await import('@/utils/node-initialization')
        const inspection = await inspectInitialization()
        if (!canEnterNodeWorkspace(inspection)) {
          next({ path: '/demo/node/initialize', replace: true })
          return
        }
        demoWorkspaceReady = true
      }
    }
    const permissionStore = usePermissionStore()
    if (!permissionStore.routesLoaded) {
      await registerDynamicRoutes()
      next({ ...to, replace: true })
      return
    }
    const rawPath = originalPath(to.path)
    if (rawPath === '/' || (principal === 'NODE' && rawPath === '/index')) {
      next({ path: landingPath({ principalType: principal }), replace: true })
      return
    }
    to.meta.title && useSettingsStore().setTitle(to.meta.title)
    next()
  } catch (error) {
    useUserStore().clearSession()
    next({ path: '/demo', query: { reason: error?.message || '演示会话不可用，请重新解析节点。' }, replace: true })
  } finally { NProgress.done() }
})

router.afterEach(() => NProgress.done())
