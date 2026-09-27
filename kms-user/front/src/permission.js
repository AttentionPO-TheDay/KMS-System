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
import { adminConsoleUrl } from '@/config/app-bases'
import { isAdminLevel } from '@/utils/role'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login', '/register']

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
        useUserStore().getInfo().then(() => {
          isRelogin.show = false
          // D9：管理员登录后落在管理控制台，用户前台不向管理员开放。
          // 目标是一个独立前端应用，整页跳转即可，不会与本站路由形成重定向环。
          if (isAdminLevel(useUserStore().roleLevel)) {
            window.location.replace(adminConsoleUrl())
            return
          }
          usePermissionStore().generateRoutes().then(accessRoutes => {
            accessRoutes.forEach(route => {
              if (!isHttp(route.path)) {
                router.addRoute(route)
              }
            })
            next({ ...to, replace: true })
          })
        }).catch(err => {
          useUserStore().logOut().then(() => {
            ElMessage.error(err)
            next({ path: '/' })
          })
        })
      } else if (usePermissionStore().sidebarRouters.length === 0) {
        // 这里修的是「普通用户登录后侧边栏空白、刷新一下才出来」（2026-09-26）。
        // 成因：登录页在 SPA 内跳转前已经调过 getInfo()，于是 roles 非空，
        // 上面那个分支不会进，**动态路由就永远没生成**，侧边栏自然是空的；
        // 刷新时 roles 从空开始，守卫走完整流程，菜单才出现。
        // 管理员碰不到：他们登录后是整页跳转到管理端，等于重新加载。
        usePermissionStore().generateRoutes().then(accessRoutes => {
          accessRoutes.forEach(route => {
            if (!isHttp(route.path)) {
              router.addRoute(route)
            }
          })
          next({ ...to, replace: true })
        }).catch(err => {
          // 生成失败不能把用户卡在空白页里，放行并提示重试
          ElMessage.error(err?.message || '加载菜单失败，请刷新重试')
          next()
        })
      } else {
        next()
      }
    }
  } else {
    // 没有token
    if (isWhiteList(to.path)) {
      // 在免登录白名单，直接进入
      next()
    } else {
      next(`/login?redirect=${to.fullPath}`) // 否则全部重定向到登录页
      NProgress.done()
    }
  }
})

router.afterEach(() => {
  NProgress.done()
})
