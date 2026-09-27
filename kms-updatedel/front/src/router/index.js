import { createWebHistory, createRouter } from 'vue-router'
/* Layout */
import Layout from '@/layout'

/*
 * 静态路由：只保留「框架级」页面（登录、重定向、首页、错误页、个人中心）。
 *
 * 业务页面（密钥生成/更新/回收/查询/权限审批/算法说明/系统管理等）
 * 一律**不在此定义**，而是由后端 sys_menu 下发、经 store/modules/permission.js
 * 转成动态路由。这样做的好处：
 *   1. 菜单只有唯一真实来源（sys_menu），不会出现前后端两份菜单叠加
 *   2. 分组与排序由 sys_menu 的 parent_id / order_num 控制，前端无需维护
 *   3. 不同角色的可见菜单可直接在「系统管理 → 菜单管理」里调整
 *
 * 此前业务路由同时写死在这里、又存在于 sys_menu，
 * 导致侧边栏出现重复项；且 permission.js 里的白名单又把业务菜单裁掉，
 * 管理员反而看不到业务入口。两处问题已一并移除。
 */
export const constantRoutes = [
  {
    path: '/redirect',
    component: Layout,
    hidden: true,
    children: [
      {
        path: '/redirect/:path(.*)',
        component: () => import('@/views/redirect/index.vue')
      }
    ]
  },
  {
    path: '/login',
    component: () => import('@/views/login.vue'),
    hidden: true
  },
  // ⚠️ 「节点鉴权」的路由**不在这里**，它由 sys_menu 下发（migration 25）。
  //
  // 这里曾经额外静态注册过一份 `/nodeauth`，注释写的是"DB 菜单行同时插入，
  // 只为让它出现在侧边栏"。结果是本文件开头警告过的那个坑又发生了一次，
  // 而且后果比"侧边栏重复"严重得多（2026-09-24 实测）：
  //
  //   1. **两条路由记录同指一个路径** —— 静态的 name=NodeAuthorization 与
  //      后端下发的 name=Index，于是页签栏里出现两个一模一样的「节点鉴权」；
  //   2. 后端按菜单 path 首字母大写生成路由名，菜单 9006 的 path 是 `index`，
  //      于是下发路由的 name 也叫 **`Index`** —— 与下面仪表盘的 name 撞名。
  //      vue-router 4 在 addRoute 遇到重名时会**先移除旧路由**，
  //      所以仪表盘 `/index` 被整个顶掉，`router.resolve('/index')` 只剩兜底
  //      `/:pathMatch(.*)*`。现象就是用户说的"总览仪表盘界面不存在"：
  //      点那个常驻标签页（affix）什么也打不开。
  //
  // 修法：业务页只留 sys_menu 一个来源（就是本文件开头写的约定）；
  // 同时把仪表盘的路由名改成 `Dashboard`，让它不再可能与任何以 `index`
  // 为路径的菜单撞名 —— 这类撞名不该靠"记得别用某个名字"来避免。
  {
    path: '',
    component: Layout,
    redirect: '/index',
    children: [
      {
        path: '/index',
        component: () => import('@/views/index.vue'),
        name: 'Dashboard',
        meta: { title: '总览仪表盘', icon: 'dashboard', affix: true }
      }
    ]
  },
  {
    path: '/user',
    component: Layout,
    hidden: true,
    redirect: 'noredirect',
    children: [
      {
        path: 'profile',
        component: () => import('@/views/system/user/profile/index.vue'),
        name: 'Profile',
        meta: { title: '个人中心', icon: 'user' }
      }
    ]
  },
  {
    path: '/401',
    component: () => import('@/views/error/401.vue'),
    hidden: true
  },
  {
    path: '/:pathMatch(.*)*',
    component: () => import('@/views/error/404.vue'),
    hidden: true
  }
]

/*
 * 动态路由：从列表页进入的「隐藏详情页」。
 *
 * 这些页面不出现在侧边栏（hidden: true），因此不能放进 sys_menu——它们靠
 * 列表页里的 router.push / router-link 带参数进入，路径含 :id 占位符。
 * permissions 与 sys_menu 里的按钮权限串保持一致，由 permission.js 的
 * filterDynamicRoutes 校验后 router.addRoute 注册。
 *
 * 注意：此前这里是空数组，导致三个入口全部落到 catch-all 的 404 页：
 *   - 系统管理 → 用户管理 → 分配角色
 *   - 系统管理 → 角色管理 → 分配用户
 *   - 系统管理 → 字典管理 → 字典数据（列表里的字典类型链接）
 * 上游 RuoYi 原本就有这些定义，迁移时被漏掉了，现补回。
 * monitor/job-log 与 tool/gen-edit 未补：本项目没有对应页面，也无菜单入口。
 */
export const dynamicRoutes = [
  {
    path: '/system/user-auth',
    component: Layout,
    hidden: true,
    permissions: ['system:user:edit'],
    children: [
      {
        path: 'role/:userId(\\d+)',
        component: () => import('@/views/system/user/authRole.vue'),
        name: 'AuthRole',
        meta: { title: '分配角色', activeMenu: '/system/user' }
      }
    ]
  },
  {
    path: '/system/role-auth',
    component: Layout,
    hidden: true,
    permissions: ['system:role:edit'],
    children: [
      {
        path: 'user/:roleId(\\d+)',
        component: () => import('@/views/system/role/authUser.vue'),
        name: 'AuthUser',
        meta: { title: '分配用户', activeMenu: '/system/role' }
      }
    ]
  },
  {
    path: '/system/dict-data',
    component: Layout,
    hidden: true,
    permissions: ['system:dict:list'],
    children: [
      {
        path: 'index/:dictId(\\d+)',
        component: () => import('@/views/system/dict/data.vue'),
        name: 'Data',
        meta: { title: '字典数据', activeMenu: '/system/dict' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: constantRoutes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    return { top: 0 }
  },
});

export default router;