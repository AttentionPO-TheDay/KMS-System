import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/workbench'
  },
  {
    path: '/lifecycle',
    redirect: '/updatedel'
  },
  {
    path: '/workbench',
    name: 'Workbench',
    component: () => import('@/views/workbench/WorkbenchView.vue')
  },
  {
    path: '/generate',
    name: 'Generate',
    component: () => import('@/views/generate/GenerateView.vue')
  },
  {
    path: '/updatedel',
    name: 'Updatedel',
    component: () => import('@/views/lifecycle/LifecycleView.vue')
  },
  {
    path: '/distribute',
    name: 'Distribute',
    component: () => import('@/views/distribute/DistributeView.vue')
  },
  {
    path: '/permissions',
    name: 'Permissions',
    component: () => import('@/views/permissions/PermissionView.vue')
  }
]

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})
