import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/layout'

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
  {
    path: '/register',
    component: () => import('@/views/register.vue'),
    hidden: true
  },
  {
    path: "/:pathMatch(.*)*",
    component: () => import('@/views/error/404.vue'),
    hidden: true
  },
  {
    path: '/401',
    component: () => import('@/views/error/401.vue'),
    hidden: true
  },
  {
    path: '',
    component: Layout,
    redirect: '/workbench',
    children: [
      {
        path: 'workbench',
        component: () => import('@/views/workbench/WorkbenchView.vue'),
        name: 'Workbench',
        meta: { title: '工作台', icon: 'dashboard', affix: true }
      }
    ]
  },
  {
    path: '/lifecycle',
    redirect: '/user_actions/updatedel',
    hidden: true
  },
  {
    path: '/generate',
    redirect: '/user_actions/generate',
    hidden: true
  },
  {
    path: '/updatedel',
    redirect: '/user_actions/updatedel',
    hidden: true
  },
  {
    path: '/distribute',
    redirect: '/user_actions/distribute',
    hidden: true
  },
  {
    path: '/permissions',
    redirect: '/user_actions/permissions',
    hidden: true
  },
  {
    path: '/user_actions',
    component: Layout,
    hidden: false,
    name: 'UserActions',
    meta: { title: '用户中心', icon: 'user' },
    children: [
      {
        path: 'generate',
        name: 'Generate',
        component: () => import('@/views/generate/GenerateView.vue'),
        meta: { title: '生成申请', icon: 'edit' }
      },
      {
        path: 'updatedel',
        name: 'Updatedel',
        component: () => import('@/views/lifecycle/LifecycleView.vue'),
        meta: { title: '更新与回收', icon: 'time-range' }
      },
      {
        path: 'distribute',
        name: 'Distribute',
        component: () => import('@/views/distribute/DistributeView.vue'),
        meta: { title: '分发下载', icon: 'download' }
      },
      {
        path: 'permissions',
        name: 'Permissions',
        component: () => import('@/views/permissions/PermissionView.vue'),
        meta: { title: '权限管理', icon: 'lock' }
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
  }
]

// 动态路由
export const dynamicRoutes = [
]

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: constantRoutes,
  scrollBehavior() {
    return { top: 0 }
  }
})
