import { createRouter, createWebHistory } from 'vue-router'
import { token } from '../auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('../views/ChatView.vue'),
    },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})

// 登录守卫:未登录一律回登录页;已登录访问登录页则直接进问答页
router.beforeEach((to) => {
  if (!to.meta.public && !token.value) return { name: 'login' }
  if (to.name === 'login' && token.value) return { name: 'chat' }
})

export default router
