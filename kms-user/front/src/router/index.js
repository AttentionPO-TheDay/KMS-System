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
    path: '/generate',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        name: 'Generate',
        component: () => import('@/views/generate/GenerateView.vue'),
        meta: { title: '密钥生成', icon: 'edit' }
      }
    ]
  },
  {
    path: '/lifecycle',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        name: 'Updatedel',
        component: () => import('@/views/lifecycle/LifecycleView.vue'),
        meta: { title: '更新与回收', icon: 'time-range' }
      }
    ]
  },
  {
    path: '/distribute',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        name: 'Distribute',
        component: () => import('@/views/distribute/DistributeView.vue'),
        // 改名为「密钥分发」：它已经从"只读记录页"变成真正的分发操作页（P3 步骤 9）
        meta: { title: '密钥分发', icon: 'download' }
      }
    ]
  },
  {
    // 对称密钥查看（P3 步骤 9）：分发给我本人的信封。
    // 服务端只存密文，明文对称密钥由分发模块持有，用户只能用自己的密钥文件解开。
    path: '/symmetric-keys',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        name: 'SymmetricKeys',
        component: () => import('@/views/distribute/SymmetricKeysView.vue'),
        // 图标用 lock：原先写的 'key' 在本前端的图标集里**不存在**
        // （src/assets/icons/svg 下没有 key.svg），于是这一项在侧边栏里没有图标。
        // 注意别再用未登记的图标名 —— 缺图标不报错，只是"那个位置空着"，很难发现。
        meta: { title: '对称密钥查看', icon: 'lock' }
      }
    ]
  },
  {
    // 我的操作日志：密钥操作记录 + 系统操作日志 + 登录日志，全部由服务端
    // 按令牌中的 user_id 强制过滤，前端不传用户号（见 D14 / Q8）。
    path: '/my-logs',
    component: Layout,
    hidden: false,
    children: [
      {
        path: 'index',
        name: 'MyLogs',
        component: () => import('@/views/logs/MyLogsView.vue'),
        meta: { title: '我的操作日志', icon: 'log' }
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
