import { createWebHistory, createRouter } from 'vue-router'
import Layout from '@/layout'

const constantRoutes = [
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
    component: () => import('@/views/login/index.vue'),
    hidden: true
  },
  {
    path: '/register',
    component: () => import('@/views/register/index.vue'),
    hidden: true
  },
  {
    path: '/userKeys',
    component: () => import('@/views/userKeys/index.vue'),
    hidden: true
  },
  {
    path: '/publickeys',
    component: () => import('@/views/publickeys/index.vue'),
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
    redirect: '/index',
    children: [
      {
        path: '/index',
        component: () => import('@/views/index/index.vue'),
        name: 'Index',
        meta: { title: '首页', icon: 'dashboard', affix: true }
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
        component: () => import('@/views/system/user/profile/index'),
        name: 'Profile',
        meta: { title: '个人中心', icon: 'user' }
      }
    ]
  },
  {
    path: '/permission/request',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        component: () => import('@/views/permission/request/index.vue'),
        name: 'GeneratePermissionRequest',
        meta: { title: '生成域权限审批', icon: 'edit' }
      }
    ]
  }
]

const dynamicRoutes = [
  {
    path: '/generate/keygenerate',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        component: () => import('@/views/generate/index.vue'),
        name: 'KeyGenerate',
        meta: { title: '密钥生成', icon: 'key' }
      }
    ]
  },
  {
    path: '/generate/history',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        component: () => import('@/views/generateHistory/index.vue'),
        name: 'KeyGenerateHistory',
        meta: { title: '生成历史', icon: 'history' }
      }
    ]
  },
  {
    path: '/generate/commonparam',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        component: () => import('@/views/commonParam/index.vue'),
        name: 'CommonParam',
        meta: { title: '公共参数', icon: 'param' }
      }
    ]
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes: constantRoutes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    return { top: 0 }
  }
})

export { constantRoutes, dynamicRoutes }

export default router
