import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘' } },
  { path: '/accounts', name: 'accounts', component: () => import('@/views/Accounts.vue'), meta: { title: '账号' } },
  { path: '/crawl', name: 'crawl', component: () => import('@/views/Crawl.vue'), meta: { title: '采集' } },
  { path: '/search', name: 'search', component: () => import('@/views/Search.vue'), meta: { title: '搜索' } },
  { path: '/live', name: 'live', component: () => import('@/views/Live.vue'), meta: { title: '直播间' } },
  { path: '/messages', name: 'messages', component: () => import('@/views/Messages.vue'), meta: { title: '私信' } },
  { path: '/interactions', name: 'interactions', component: () => import('@/views/Interactions.vue'), meta: { title: '互动' } },
  { path: '/analysis', name: 'analysis', component: () => import('@/views/Analysis.vue'), meta: { title: '分析' } },
  { path: '/tasks', name: 'tasks', component: () => import('@/views/Tasks.vue'), meta: { title: '任务' } },
  { path: '/downloads', name: 'downloads', component: () => import('@/views/Downloads.vue'), meta: { title: '下载' } },
]

const router = createRouter({ history: createWebHistory(), routes })
export default router
