import { createWebHistory, createRouter } from 'vue-router'
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
        component: () => import('@/views/index.vue'),
        name: 'Index',
        meta: { title: '首页', icon: 'dashboard', affix: true }
      }
    ]
  },
  {
    path: '/distribute',
    component: Layout,
    hidden: false,
    redirect: 'noredirect',
    meta: { title: '密钥分发', icon: 'tree' },
    children: [
      {
        path: 'record',
        component: () => import('@/views/distribute/record.vue'),
        name: 'DistributeRecord',
        meta: { title: '分发记录', icon: 'list' }
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

export const dynamicRoutes = [
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
