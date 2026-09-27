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
import { resolvePrincipalType, PRINCIPAL_NODE } from '@/utils/principal'
import { fetchNodeInitStatus } from '@/utils/node-init-status'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login']

const isWhiteList = (path) => {
  return whiteList.some(pattern => isPathMatch(pattern, path))
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
            // ACTIVE 节点：正常放行（菜单仍是 sys_menu 下发的那套）。
          }

          usePermissionStore().generateRoutes().then(accessRoutes => {
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
              // 根据roles权限生成可访问的路由表
              accessRoutes.forEach(route => {
                if (!isHttp(route.path)) {
                  router.addRoute(route); // 动态添加可访问路由表
                }
              });
              next({ ...to, replace: true }); // hack方法 确保addRoutes已完成
            } else {
              // 非管理员且非节点：整页跳本应用的 401 提示页。
              // 用整页跳转（而非 next()）是为了丢掉本次导航上下文，
              // 避免守卫在 addRoute 之后被再次触发形成循环。
              window.location.replace(`${import.meta.env.BASE_URL}401`);
            }
          })
        }).catch(err => {
          useUserStore().logOut().then(() => {
            ElMessage.error(err)
            next({ path: '/' })
          })
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
    next(`/login?redirect=${to.fullPath}`)
    NProgress.done()
  }
})

router.afterEach(() => {
  NProgress.done()
})
