import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/lattice', redirect: '/lattice/offline-trapdoor' },
  ...['parallel-sampling', 'offline-trapdoor', 'basis-delegation'].map(caseId => ({
    path: `/lattice/${caseId}`, name: `lattice-${caseId}`,
    component: () => import('../views/LatticeTestPage.vue'), props: { caseId }
  })),
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
