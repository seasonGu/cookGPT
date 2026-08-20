// 极简登录态:token/用户名存 localStorage,用 ref 做响应式,各组件共享
import { ref } from 'vue'

const TOKEN_KEY = 'cookgpt_token'
const USERNAME_KEY = 'cookgpt_username'

export const token = ref(localStorage.getItem(TOKEN_KEY) || '')
export const username = ref(localStorage.getItem(USERNAME_KEY) || '')

export function setAuth(newToken, newUsername) {
  token.value = newToken
  username.value = newUsername
  localStorage.setItem(TOKEN_KEY, newToken)
  localStorage.setItem(USERNAME_KEY, newUsername)
}

export function clearAuth() {
  token.value = ''
  username.value = ''
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USERNAME_KEY)
}
