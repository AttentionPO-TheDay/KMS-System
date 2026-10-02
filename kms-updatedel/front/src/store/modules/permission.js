import auth from '@/plugins/auth'
import router, { constantRoutes, dynamicRoutes } from '@/router'
import { getRouters } from '@/api/menu'
import Layout from '@/layout/index'
import ParentView from '@/components/ParentView'
import InnerLink from '@/layout/components/InnerLink'
import { filterSidebarByPrincipal } from '@/utils/landing'
import { applyNoSidebarMeta } from '@/utils/subsystems'
import useUserStore from '@/store/modules/user'

// 匹配views里面所有的.vue文件
const modules = import.meta.glob('./../../views/**/*.vue')

// 说明：此处原先有 ADMIN_ROUTE_WHITELIST / ADMIN_ROUTE_ORDER，
// 把后端菜单裁剪到只剩 system 与 log 两组。后果是**所有 KMS 业务菜单**
// （密钥生成、密钥更新、密钥回收、权限审批、密钥查询等）被一并过滤掉，
// 管理员登录后侧边栏里根本看不到这些入口——这正是「没有可进入的接口」的根因。
// 现改为直接采用后端 sys_menu 返回的完整菜单树：
//   - 菜单分组与排序统一由 sys_menu 的 parent_id / order_num 决定
//   - 不存在的页面（component 指向缺失文件）已在数据库迁移中删除
// 这样菜单只有一个真实来源，前端不再做二次裁剪。

const usePermissionStore = defineStore(
  'permission',
  {
    state: () => ({
      routes: [],
      addRoutes: [],
      defaultRoutes: [],
      topbarRouters: [],
      sidebarRouters: [],
      /**
       * 动态路由是否已经走过 `generateRoutes()`。
       *
       * 为什么需要这个显式标志（2026-09-30 实测踩到）：
       * 判断"要不要生成路由"原先只看 `userStore.roles.length === 0`。
       * 但有一条路径会**先有 roles、后需要路由**：
       *   PENDING_INIT 节点登录 → 守卫把它送去 `/node-init` 引导页 →
       *   那条分支在 `generateRoutes()` **之前**就 return 了，
       *   于是整个初始化过程中动态路由一条都没注册。
       *   用户在引导页点「进入工作台」是 SPA 内跳转，守卫看到 roles 已有
       *   就直接放行 —— 而 `/workbench` 从未 addRoute，落到 catch-all 404。
       *
       * `roles.length` 只说明"身份取过了"，不说明"路由注册过了"，
       * 两者是不同的事，得分别记。
       */
      routesLoaded: false
    }),
    actions: {
      setRoutes(routes) {
        this.addRoutes = routes
        // `routes`（= constantRoutes + 动态菜单）是**页签栏 affix 标签**与
        // **顶栏搜索**的数据源。它们必须与侧边栏用同一份过滤结果，否则会出现
        // "侧边栏里没有、页签栏却挂着"的条目 —— 实测（2026-09-30）节点端
        // 页签栏一直挂着「总览仪表盘」（管理端页面），点它打不开。
        //
        // 用同一份过滤也是口径上对的：侧边栏里到不了的地方，搜索也不该找到。
        const userStore = useUserStore()
        this.routes = filterSidebarByPrincipal(
          constantRoutes.concat(routes),
          userStore.roleLevel,
          userStore.principalType
        )
      },
      setDefaultRoutes(routes) {
        this.defaultRoutes = constantRoutes.concat(routes)
      },
      setTopbarRoutes(routes) {
        this.topbarRouters = routes
      },
      setSidebarRouters(routes) {
        this.sidebarRouters = routes
      },
      generateRoutes(roles) {
        return new Promise(resolve => {
          // 向后端请求路由数据（完整菜单树，不再做前端裁剪）
          getRouters().then(res => {
            const sdata = JSON.parse(JSON.stringify(res.data))
            const rdata = JSON.parse(JSON.stringify(res.data))
            const defaultData = JSON.parse(JSON.stringify(res.data))
            const sidebarRoutes = filterAsyncRouter(sdata)
            const rewriteRoutes = filterAsyncRouter(rdata, false, true)
            const defaultRoutes = filterAsyncRouter(defaultData)
            const asyncRoutes = filterDynamicRoutes(dynamicRoutes)
            asyncRoutes.forEach(route => { router.addRoute(route) })
            // 给"不要侧边栏"的页面打 meta 标记。
            //
            // ⚠️ 只对 **NODE** 打：工作台对节点端是"刚进入的主页面"（整页展示
            //    子系统入口与数据，不该旁边再挂菜单），而管理端的落地页是 `/index`，
            //    其侧边栏照常。
            //
            //    按主体分流的判断放在**这里**（而不是让 layout 自己去判断），
            //    是为了与其它按主体收敛的逻辑（`filterSidebarByPrincipal`）
            //    待在同一处 —— 改的时候不容易只改一半。
            //    标记打上之后，layout 直接读 `route.meta.hideSidebar` 即可，
            //    那是唯一真实来源，不必再在 store 里存一份路径清单。
            //
            //    必须在 `setRoutes` / `addRoute` **之前**做：那两个都会消费 meta。
            const principalForMeta = useUserStore().principalType
            if (String(principalForMeta).toUpperCase() === 'NODE') {
              applyNoSidebarMeta(rewriteRoutes)
              applyNoSidebarMeta(sidebarRoutes)
            }
            this.setRoutes(rewriteRoutes)
            // 侧边栏按主体收敛：
            //   NODE  —— 摘掉管理端静态页（仪表盘等），节点不该看到管理端入口
            //   超管  —— 摘掉节点端那一棵（后端对它跳过 sys_role_menu，两棵树都下发）
            // 判据与理由见 utils/landing.js 的 filterSidebarByPrincipal。
            this.setSidebarRouters(
              filterSidebarByPrincipal(
                constantRoutes.concat(sidebarRoutes),
                useUserStore().roleLevel,
                useUserStore().principalType
              )
            )
            this.setDefaultRoutes(sidebarRoutes)
            this.setTopbarRoutes(defaultRoutes)
            // 标记"路由已注册"。守卫用它区分"身份取过了"与"路由注册过了"——
            // 详见 state 里 routesLoaded 的注释。
            this.routesLoaded = true
            resolve(rewriteRoutes)
          })
        })
      }
    }
  })

// 遍历后台传来的路由字符串，转换为组件对象
function filterAsyncRouter(asyncRouterMap, lastRouter = false, type = false) {
  return asyncRouterMap.filter(route => {
    if (type && route.children) {
      route.children = filterChildren(route.children)
    }
    if (route.component) {
      // Layout ParentView 组件特殊处理
      if (route.component === 'Layout') {
        route.component = Layout
      } else if (route.component === 'ParentView') {
        route.component = ParentView
      } else if (route.component === 'InnerLink') {
        route.component = InnerLink
      } else {
        route.component = loadView(route.component)
      }
    }
    if (route.children != null && route.children && route.children.length) {
      route.children = filterAsyncRouter(route.children, route, type)
    } else {
      delete route['children']
      delete route['redirect']
    }
    return true
  })
}

function filterChildren(childrenMap, lastRouter = false) {
  var children = []
  childrenMap.forEach((el, index) => {
    if (el.children && el.children.length) {
      if (el.component === 'ParentView' && !lastRouter) {
        el.children.forEach(c => {
          c.path = el.path + '/' + c.path
          if (c.children && c.children.length) {
            children = children.concat(filterChildren(c.children, c))
            return
          }
          children.push(c)
        })
        return
      }
    }
    if (lastRouter) {
      el.path = lastRouter.path + '/' + el.path
      if (el.children && el.children.length) {
        children = children.concat(filterChildren(el.children, el))
        return
      }
    }
    children = children.concat(el)
  })
  return children
}

// 动态路由遍历，验证是否具备权限
export function filterDynamicRoutes(routes) {
  const res = []
  routes.forEach(route => {
    if (route.permissions) {
      if (auth.hasPermiOr(route.permissions)) {
        res.push(route)
      }
    } else if (route.roles) {
      if (auth.hasRoleOr(route.roles)) {
        res.push(route)
      }
    }
  })
  return res
}

export const loadView = (view) => {
  let res;
  for (const path in modules) {
    const dir = path.split('views/')[1].split('.vue')[0];
    if (dir === view) {
      res = () => modules[path]();
    }
  }
  return res;
}

export default usePermissionStore
