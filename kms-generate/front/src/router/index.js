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
    component: () => import('@/views/login.vue'),
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
    path: '',
    component: Layout,
    hidden: false,
    children: [
      {
        path: '/algorithm-quick',
        component: () => import('@/views/algorithm/quickView.vue'),
        name: 'AlgorithmQuickView',
        meta: { title: '生成算法速览', icon: 'guide' }
      }
    ]
  },
  {
    path: '',
    component: Layout,
    hidden: false,
    children: [
      {
        path: '/algorithm-process',
        component: () => import('@/views/algorithm/processView.vue'),
        name: 'AlgorithmProcessView',
        meta: { title: '生成计算逻辑揭秘', icon: 'data-line' }
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
    path: '/permission/request',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        component: () => import('@/views/permission/request/index.vue'),
        name: 'GeneratePermissionRequest',
        meta: { title: '系统权限审批', icon: 'edit' }
      }
    ]
  },
  {
    path: '/generate/keygenerate',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        component: () => import('@/views/generate/index.vue'),
        name: 'KeyGenerate',
        meta: { title: '密钥生成', icon: 'lock' }
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
        meta: { title: '生成历史', icon: 'chart' }
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
        meta: { title: '公共参数', icon: 'list' }
      }
    ]
  },
  {
    path: '/query',
    component: Layout,
    redirect: '/query/key-list',
    meta: { title: '密钥查询', icon: 'search' },
    children: [
      {
        path: 'key-list',
        component: () => import('@/views/query/keyList/index.vue'),
        name: 'KeyQuery',
        meta: { title: '用户密钥查询', icon: 'list' }
      },
      {
        path: 'public-keys',
        component: () => import('@/views/publickeys/index.vue'),
        name: 'PublicKeyQuery',
        meta: { title: '公钥查询', icon: 'lock' }
      },
      {
        path: 'blockchain',
        component: () => import('@/views/query/keyList/index.vue'),
        name: 'BlockchainView',
        meta: { title: '区块链查看', icon: 'link' }
      },
      {
        path: 'key-users',
        component: () => import('@/views/query/businessUsers/index.vue'),
        name: 'KeyUserManagement',
        meta: { title: '密钥用户管理', icon: 'peoples' }
      }
    ]
  }
]

const dynamicRoutes = []

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
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
