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
import { userConsoleUrl, userLoginUrl } from '@/config/app-bases'
import { isAdminLevel } from '@/utils/role'

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
        useUserStore().getInfo().then((res) => {
          isRelogin.show = false
          usePermissionStore().generateRoutes().then(accessRoutes => {
            // 管理控制台只对管理员开放，判据是 role_level <= 0（D9 / D13）。
            //
            // 原实现按 role_id === 1 || role_id === 2 判定，有两个问题：
            //   1. role_id=2 是「普通角色」，普通用户恰好持有它 —— 等于对普通用户
            //      开放了整个管理端（能否看到页面只剩 sys_role_menu 一层拦截）；
            //   2. test01/user01 持有的是 role_id=3，而 sys_role 里根本没有 3 号角色，
            //      他们被判成非管理员后会被踢到 /userKeys，与其 role_level=2 的
            //      实际身份并不一致。
            // 统一改用 role_level，与用户前台、生命周期页、权限页的判据完全一致。
            if (isAdminLevel(useUserStore().roleLevel)) {
              // 根据roles权限生成可访问的路由表
              accessRoutes.forEach(route => {
                if (!isHttp(route.path)) {
                  router.addRoute(route); // 动态添加可访问路由表
                }
              });
              next({ ...to, replace: true }); // hack方法 确保addRoutes已完成
            } else {
              // 非管理员不得停留在管理端：整页跳回用户前台。
              // 两应用同源且共用 Admin-Token，因此不会要求二次登录。
              window.location.replace(userConsoleUrl());
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
    // 没有 token —— 整页跳到**唯一登录入口**（用户前台），不在本应用里再显示一套登录页。
    //
    // 依据是 D9（见 config/app-bases.js 的注释）：系统只有一个登录入口（kms-user），
    // 登录后按 roleLevel 分流；管理端不是入口。此前这里 next('/login') 会把管理端
    // 自己的 login.vue 渲染出来 —— 于是系统里出现了**两个登录页**，而且两者的
    // 验证码策略还不一样（管理端后端有 KMS_CAPTCHA_ENABLED 覆盖、用户前台后端没有），
    // 表现为"有的登录页要验证码、有的不要"，看起来像 bug（2026-09-24 用户反馈）。
    //
    // 两个应用同源、共用 Admin-Token，跳过去登录一次即可；管理员登录后由
    // 用户前台的守卫按 roleLevel 送回本应用。
    window.location.replace(userLoginUrl())
    NProgress.done()
  }
})

router.afterEach(() => {
  NProgress.done()
})
