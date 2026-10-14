import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/lifecycle', name: 'LifecycleAudit', component: () => import('../views/LifecycleAudit.vue') },
  {
    path: '/',
    redirect: '/load-test'
  },
  {
    path: '/load-test',
    name: 'LoadTest',
    component: () => import('../views/LoadTestView.vue')
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
