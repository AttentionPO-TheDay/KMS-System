import router from './router'
import { ElMessage } from 'element-plus'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { getToken } from '@/utils/auth'
import { isHttp, isPathMatch } from '@/utils/validate'
import { isRelogin } from '@/utils/request'
import useUserStore from '@/store/modules/user'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import { isAdminLevel } from '@/utils/role'
import { resolvePrincipalType, PRINCIPAL_NODE, PRINCIPAL_ADMIN } from '@/utils/principal'
import { isAdminLanding, landingPath } from '@/utils/landing'
import { fetchNodeInitStatus } from '@/utils/node-init-status'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login']

const isWhiteList = (path) => {
  return whiteList.some(pattern => isPathMatch(pattern, path))
}

/**
 * 生成动态路由并逐条 `addRoute` 注册到 vue-router。
 *
 * 抽出来是因为有**两条**路径需要它：正常登录流程，以及
 * "身份已取过、但路由还没注册"的补注册（见守卫里 rolesLoaded 那段）。
 * 写成两处的话，迟早只改一处 —— 而这类"漏注册"的表现是 404，
 * 不是报错，很难追。
 *
 * @returns {Promise<Array>} 可访问路由表
 */
function registerDynamicRoutes() {
  return usePermissionStore().generateRoutes().then(accessRoutes => {
    accessRoutes.forEach(route => {
      if (!isHttp(route.path)) {
        router.addRoute(route) // 动态添加可访问路由表
      }
    })
    return accessRoutes
  })
}

// router.beforeEach((to, from, next) => {
//   NProgress.start()
//   if (getToken()) {
//     to.meta.title && useSettingsStore().setTitle(to.meta.title)
//     /* has token*/
//     if (to.path === '/login') {
//       next({ path: '/' })
//       NProgress.done()
//     } else if (isWhiteList(to.path)) {
//       next()
//     } else {
//       if (useUserStore().roles.length === 0) {
//         isRelogin.show = true
//         // 判断当前用户是否已拉取完user_info信息
//         useUserStore().getInfo().then(() => {
//           isRelogin.show = false
//           usePermissionStore().generateRoutes().then(accessRoutes => {
//             // 根据roles权限生成可访问的路由表
//             accessRoutes.forEach(route => {
//               if (!isHttp(route.path)) {
//                 router.addRoute(route) // 动态添加可访问路由表
//               }
//             })
//             next({ ...to, replace: true }) // hack方法 确保addRoutes已完成
//           })
//         }).catch(err => {
//           useUserStore().logOut().then(() => {
//             ElMessage.error(err)
//             next({ path: '/' })
//           })
//         })
//       } else {
//         next()
//       }
//     }
//   } else {
//     // 没有token
//     if (isWhiteList(to.path)) {
//       // 在免登录白名单，直接进入
//       next()
//     } else {
//       next(`/login?redirect=${to.fullPath}`) // 否则全部重定向到登录页
//       NProgress.done()
//     }
//   }
// })

router.beforeEach((to, from, next) => {
  NProgress.start()
  if (getToken()) {
    to.meta.title && useSettingsStore().setTitle(to.meta.title)
    /* has token*/
    if (to.path === '/login') {
      next({ path: '/' })
      NProgress.done()
    } else if (isWhiteList(to.path)) {
      next()
    } else {
      if (useUserStore().roles.length === 0) {
        isRelogin.show = true
        // 判断当前用户是否已拉取完user_info信息
        useUserStore().getInfo().then(async (res) => {
          isRelogin.show = false

          // 阶段 2：先按**主体类型**分流，再谈准入。
          //
          // 判据全部收敛到 utils/principal.js 的 resolvePrincipalType()，
          // 不在守卫里散写 —— 这套判据在顶栏、引导页、各业务页入口都要用，
          // 散着写必然漂移（仓库里 role_level 曾因三处各写一份而分裂过）。
          const principal = resolvePrincipalType({
            principalType: useUserStore().principalType,
            roleLevel: useUserStore().roleLevel
          })

          // 单一登录入口的身份校验：登录页选了"管理员"还是"节点"，
          // 必须与服务端认定的身份一致，不一致就**拒绝登录**。
          //
          // ⚠️ 判断权必须在**这里**，不能在 login.vue 里做。
          //    登录页拿不到真实身份 —— 那要先调 getInfo()，而本仓库有明确记录：
          //    登录页提前调 getInfo() 会把 roles 填上，随后守卫看到
          //    `roles.length !== 0` 就跳过 generateRoutes()，动态路由一条都不注册，
          //    表现为"侧边栏空白，刷新一下才出来"（见 verify-login-sidebar.mjs）。
          //    所以登录页只声明意图，真实身份一律等守卫这边 getInfo() 之后再说。
          //
          // 声明为空（刷新页面、直接敲 URL、书签进入）时不校验 ——
          // 那种情况下没有"选错身份"这回事，按服务端身份正常放行即可。
          const declared = useUserStore().declaredPrincipal
          if (declared && declared !== principal) {
            const declaredText = declared === PRINCIPAL_ADMIN ? '管理员' : '节点'
            const actualText = principal === PRINCIPAL_ADMIN ? '管理员' : '节点'
            useUserStore().clearSession()
            isRelogin.show = false
            ElMessage.error(`该账号是${actualText}，不能以${declaredText}身份登录`)
            next({ path: '/login', replace: true })
            NProgress.done()
            return
          }

          // 节点请求根路径时要改投工作台（理由见下方 NODE 分支）。
          // ⚠️ 这个标志必须声明在 `if` **之外**（2026-09-30 实测踩到）：
          //    写在 if 块里、却在 generateRoutes() 的回调里读取，块级作用域下
          //    那是一个 ReferenceError，而且发生在 .then 里，**不会**被外层
          //    catch 接住 —— 现象是节点登录后整页空白，没有报错、没有提示。
          let isRootRequest = false

          // NODE 主体：检查首次初始化状态。
          // PENDING_INIT 的节点**没有完整菜单**，不能走 generateRoutes ——
          // 直接送去引导页，那里是静态路由，不依赖菜单下发。
          if (principal === PRINCIPAL_NODE) {
            if (to.path === '/node-init') {
              next()
              NProgress.done()
              return
            }
            const status = await fetchNodeInitStatus()
            if (status === 'PENDING_INIT') {
              next({ path: '/node-init', replace: true })
              NProgress.done()
              return
            }
            // DISABLED 节点没有可用视图；如实告知而不是给一个空控制台。
            if (status === 'DISABLED') {
              window.location.replace(`${import.meta.env.BASE_URL}401`)
              NProgress.done()
              return
            }
            // ACTIVE 节点：正常放行（菜单是 sys_menu 按 role 2 下发的那棵）。
            //
            // 根路径要改落到工作台 —— 两棵菜单树见 doc/admin-node-login-design.md §11，
            // 节点端的第一个条目是「工作台」（menu 9050，path=/workbench），
            // 不是管理端的系统总览 /index。
            //
            // ⚠️ 但**不能在这里直接 next() 掉**（2026-09-30 实测踩到）：
            //    这条路径位于 generateRoutes() **之前**，此时动态路由一条都还没注册，
            //    直接跳 /workbench 会落到 SPA 的 404 兜底页 —— 页面显示
            //    "404错误！找不到网页"，而接口与菜单其实都是好的。
            //    同一个坑 `tools/verify-login-sidebar.mjs` 的注释里记过：
            //    "动态路由从未生成 → 侧边栏没数据"，只是那次表现在侧边栏、这次在落地页。
            //
            //    所以这里只记下"落地页该换"，等 generateRoutes 注册完再跳（见下方）。
            isRootRequest = isAdminLanding(to.path)
          }

          registerDynamicRoutes().then(accessRoutes => {
            // 准入判据分两类主体，**不能只留 isAdminLevel**（阶段 2）。
            //
            // 改造前这里只有 `isAdminLevel(roleLevel)` 一道门禁，它守的是
            // 「role_id=2 那条通用角色带了 system:user/role:* 管理权限」这个问题
            // （2026-09-27 实测：用 yx 的令牌能 200 读到角色/用户/操作日志列表）。
            //
            // 但节点的 role_level 也是 2 —— 只留这一道，节点完成初始化后会被
            // 当成"非管理员"整页踢到 /401，**一个业务页都进不去**。
            // 2026-09-28 实测踩到：初始化完成后访问 /workbench 落在 401。
            //
            // 所以按主体分流：
            //   ADMIN → 必须 isAdminLevel 才放行（保住上面那条防线）
            //   NODE  → 已通过前面的"初始化状态"检查（PENDING_INIT/DISABLED 都已被
            //           送走），到这里只可能是 ACTIVE 节点，应当放行。
            //           它能看到什么由 sys_menu 下发决定，与 role_level 无关。
            const allowed = principal === PRINCIPAL_NODE
              ? true
              : isAdminLevel(useUserStore().roleLevel)

            if (allowed) {
              // 路由已由 registerDynamicRoutes() 注册完毕，直接放行。
              //
              // 节点请求根路径 → 现在路由已注册，可以安全地改投工作台了。
              // 放在 addRoute **之后**是这段代码存在的全部理由，别挪上去。
              if (principal === PRINCIPAL_NODE && isRootRequest) {
                next({ path: landingPath({ principalType: principal }), replace: true })
                NProgress.done()
                return
              }

              next({ ...to, replace: true }); // hack方法 确保addRoutes已完成
            } else {
              // 非管理员且非节点：整页跳本应用的 401 提示页。
              // 用整页跳转（而非 next()）是为了丢掉本次导航上下文，
              // 避免守卫在 addRoute 之后被再次触发形成循环。
              window.location.replace(`${import.meta.env.BASE_URL}401`);
            }
          })
        }).catch(err => {
          // 旧 token 可能在 Docker/Redis 重启后已经失效。
          // 本地会话必须先清掉，且不能等待 /logout 成功：失效 token 的
          // 注销请求也可能失败，若把 next() 放在 logOut().then() 里，
          // 当前导航就会一直悬挂，表现为页面卡死。
          useUserStore().clearSession()
          isRelogin.show = false
          ElMessage.error(err?.message || err || '登录状态已失效，请重新登录')
          next({
            path: '/login',
            query: { redirect: to.fullPath },
            replace: true
          })
        })
      } else if (!usePermissionStore().routesLoaded) {
        // 身份已经取过，但**动态路由还没注册** —— 补注册再放行。
        //
        // 什么时候会走到这里（2026-09-30 实测踩到）：
        //   PENDING_INIT 节点登录 → 上方 NODE 分支把它送去 `/node-init`，
        //   而那条分支在 registerDynamicRoutes() **之前**就 return 了。
        //   于是节点在引导页完成初始化、点「进入工作台」时，
        //   `roles` 早已存在 → 原先这里直接 `next()` → `/workbench` 从未
        //   addRoute → 落到 catch-all 的 404 页。
        //
        // ⚠️ 判据必须是 routesLoaded 而**不是** roles.length：
        //    `roles.length` 只说明"身份取过了"，与"路由注册过了"是两件事。
        //    正是把两者当成一件事，才漏掉了这条路径。
        isRelogin.show = true
        registerDynamicRoutes()
          .then(() => {
            isRelogin.show = false
            // 用 replace 重走当前导航：addRoute 之后再解析一次，
            // 这次目标页在路由表里了。
            next({ ...to, replace: true })
          })
          .catch(err => {
            isRelogin.show = false
            useUserStore().clearSession()
            ElMessage.error(err?.message || err || '页面路由加载失败，请重新登录')
            next({ path: '/login', query: { redirect: to.fullPath }, replace: true })
          })
      } else {
        next()
      }
    }
  } else {
    // 没有 token —— 进本应用**自己的**登录页。
    //
    // 阶段 1（前端合并）前，这里整页跳到 kms-user 的登录页（D9「唯一登录入口」）。
    // 用户前台随本次合并退役后，那个入口已不存在，故改为回到本应用的 /login，
    // 与 request.js 里 getLoginPath() 的会话过期处理保持一致。
    //
    // ⚠️ 白名单必须**先判**，否则整页卡死（2026-09-28 实测）。
    //
    // 上一版这里直接 `next('/login?redirect=' + to.fullPath)` 就收工了，
    // 漏掉了下面这个判断。而 `isPathMatch` 是拿 `^...$` 全串锚定的正则，
    // `/login?redirect=/` **匹配不上** 模式 `/login`（query 把 $ 锚点顶掉了）。
    // 于是重定向到登录页后守卫再跑一遍：仍然没有 token → 又匹配不上白名单
    // → 再跳一次，且 redirect 的值每轮把自己套一层：
    //     /login?redirect=/login?redirect=/login?redirect=/...
    // 导航始终在守卫里被改写，**永远不提交**（实测 pushState 恒为 0），
    // 而每轮都调 NProgress.start()/done()，堆起的定时器与微任务把主线程
    // 彻底占满 —— 表现为页面白屏卡死，连 DOMContentLoaded 都不触发。
    //
    // 注意这不是"多加一层保险"：登录页本身也在白名单里，所以
    // 判到 `to.path === '/login'` 时必须放行，否则就是上面那个循环。
    if (isWhiteList(to.path)) {
      next()
      NProgress.done()
    } else {
      next(`/login?redirect=${to.fullPath}`)
      NProgress.done()
    }
  }
})

router.afterEach(() => {
  NProgress.done()
})
