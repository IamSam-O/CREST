import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('../views/LibraryView.vue'), name: 'library' },
  { path: '/banks', component: () => import('../views/BankListView.vue'), name: 'banks' },
  { path: '/banks/:id', component: () => import('../views/BankDetailView.vue'), name: 'bank-detail' },
  { path: '/exams/:id/setup', component: () => import('../views/ExamSetupView.vue'), name: 'exam-setup' },
  { path: '/exams/:id/take', component: () => import('../views/TakeView.vue'), name: 'take' },
  { path: '/instances/:id', component: () => import('../views/ResultsView.vue'), name: 'results' },
  { path: '/history', component: () => import('../views/HistoryView.vue'), name: 'history' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
