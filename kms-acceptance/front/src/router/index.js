import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/load-test'
  },
  {
    path: '/load-test',
    name: 'LoadTest',
    component: () => import('../views/LoadTestView.vue')
  },
  {
    path: '/security',
    name: 'Security',
    component: () => import('../views/SecurityView.vue')
  },
  {
    path: '/others',
    name: 'Others',
    component: () => import('../views/OthersView.vue')
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
