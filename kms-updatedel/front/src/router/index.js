import { createWebHistory, createRouter } from 'vue-router'
/* Layout */
import Layout from '@/layout'

// 公共路由
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
    path: '/updatedel/keyupdate',
    component: Layout,
    hidden: false,
    children: [
      {
        path: '',
        component: () => import('@/views/keyupdate/index.vue'),
        name: 'KeyUpdate',
        meta: { title: '密钥更新', icon: 'edit' }
      }
    ]
  },
  {
    path: '/updatedel/keydelete',
    component: Layout,
    hidden: false,
    children: [
      {
        path: '',
        component: () => import('@/views/keydelete/index.vue'),
        name: 'KeyDelete',
        meta: { title: '密钥回收', icon: 'delete' }
      }
    ]
  },
  {
    path: '/updatedel/keyautoupdate',
    component: Layout,
    hidden: false,
    children: [
      {
        path: '',
        component: () => import('@/views/keyautoupdate/index.vue'),
        name: 'KeyAutoUpdate',
        meta: { title: '自动更新', icon: 'time' }
      },
      {
        path: 'user',
        component: () => import('@/views/keyautoupdate/user.vue'),
        name: 'KeyAutoUpdateUser',
        hidden: true,
        meta: { title: '用户密钥自动更新' }
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
        name: 'PermissionRequest',
        meta: { title: '权限审批', icon: 'edit' }
      }
    ]
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

// 动态路由，基于用户权限动态去加载
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
