import { RouteRecordRaw } from 'vue-router'

/**
 * PQKDS 后量子密钥分发系统路由配置
 */
export const pqkdsRoutes: RouteRecordRaw[] = [
  {
    path: '/pqkds',
    name: 'pqkds',
    component: () => import('/@/layout/index.vue'),
    redirect: '/pqkds/dashboard',
    meta: {
      title: 'PQKDS系统',
      icon: 'iconfont icon-lock',
      isLink: '',
      isHide: false,
      isKeepAlive: true,
      isAffix: false,
      isIframe: false,
      roles: ['admin'],
      auth: ['pqkds:view']
    },
    children: [
      {
        path: '/pqkds/dashboard',
        name: 'pqkdsDashboard',
        component: () => import('/@/views/pqkds/dashboard/index.vue'),
        meta: {
          title: '系统概览',
          icon: 'iconfont icon-dashboard',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:dashboard:view']
        }
      },
      {
        path: '/pqkds/blockchain',
        name: 'pqkdsBlockchain',
        component: () => import('/@/views/pqkds/blockchain/index.vue'),
        meta: {
          title: '区块链管理',
          icon: 'iconfont icon-blockchain',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:blockchain:view']
        }
      },
      {
        path: '/pqkds/nodes',
        name: 'pqkdsNodes',
        component: () => import('/@/views/pqkds/nodes/index.vue'),
        meta: {
          title: '节点管理',
          icon: 'iconfont icon-node',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:nodes:view']
        }
      },
      {
        path: '/pqkds/sessions',
        name: 'pqkdsSessions',
        component: () => import('/@/views/pqkds/sessions/index.vue'),
        meta: {
          title: '会话管理',
          icon: 'iconfont icon-session',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:sessions:view']
        }
      },
      {
        path: '/pqkds/messages',
        name: 'pqkdsMessages',
        component: () => import('/@/views/pqkds/messages/index.vue'),
        meta: {
          title: '消息管理',
          icon: 'iconfont icon-message',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:messages:view']
        }
      },
      {
        path: '/pqkds/keys',
        name: 'pqkdsKeys',
        component: () => import('/@/views/pqkds/keys/index.vue'),
        meta: {
          title: '密钥管理',
          icon: 'iconfont icon-key',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:keys:view']
        }
      },
      {
        path: '/pqkds/logs',
        name: 'pqkdsLogs',
        component: () => import('/@/views/pqkds/logs/index.vue'),
        meta: {
          title: '操作日志',
          icon: 'iconfont icon-log',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:logs:view']
        }
      },
      {
        path: '/pqkds/key-pool',
        name: 'pqkdsKeyPool',
        component: () => import('/@/views/pqkds/keyPool/index.vue'),
        meta: {
          title: '密钥预分配',
          icon: 'iconfont icon-key',
          isLink: '',
          isHide: false,
          isKeepAlive: true,
          isAffix: false,
          isIframe: false,
          roles: ['admin'],
          auth: ['pqkds:keypool:view']
        }
      }
    ]
  }
]
