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
        path: '/algorithm-demo',
        component: () => import('@/views/algorithm/index.vue'),
        name: 'AlgorithmIntegratedView',
        meta: { title: '算法图解与演示', icon: 'guide' }
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
  // 按 D2 / 系统归属：生成域不再受理任何权限申请，后端整套生成域权限申请接口
  // 已随 P1 下线（list / submit / approve / reject / rollback / {id} / delete 全部 404）。
  // 原权限申请路由、页面与接口封装模块（api/permission/）一并删除，
  // 权限申请与审批只保留在生命周期域，不在此处重建任何替代入口。
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
