import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'NewsFeed',
    component: () => import('../views/NewsFeed.vue')
  },
  {
    path: '/event/:id',
    name: 'EventDetail',
    component: () => import('../views/EventDetail.vue')
  },
  {
    path: '/sources',
    name: 'SourceList',
    component: () => import('../views/SourceList.vue')
  },
  {
    path: '/candidates',
    name: 'CandidateQueue',
    component: () => import('../views/CandidateQueue.vue')
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
