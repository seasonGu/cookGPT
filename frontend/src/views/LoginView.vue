<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { setAuth } from '../auth'

const router = useRouter()
const mode = ref('login') // 'login' | 'register'
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  // 客户端先校验,给明确的中文提示(与后端规则一致)
  const name = username.value.trim()
  if (name.length < 3 || name.length > 32) {
    error.value = '用户名长度需为 3-32 位'
    return
  }
  if (!/^[A-Za-z0-9_一-龥]+$/.test(name)) {
    error.value = '用户名只能包含字母、数字、下划线或中文'
    return
  }
  if (password.value.length < 6) {
    error.value = '密码至少 6 位'
    return
  }
  loading.value = true
  try {
    const fn = mode.value === 'login' ? api.login : api.register
    const data = await fn(name, password.value)
    setAuth(data.token, data.username)
    router.push('/chat')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
}
</script>

<template>
  <div class="login-page">
    <div class="card">
      <div class="brand">
        <div class="logo">🍳</div>
        <h1>cookGPT</h1>
        <p class="tagline">你的 AI 私厨,想吃什么,问它就好</p>
      </div>

      <form class="form" @submit.prevent="submit">
        <label>
          <span>用户名</span>
          <input
            v-model="username"
            type="text"
            placeholder="3-32 位字母、数字、下划线或中文"
            autocomplete="username"
          />
        </label>
        <label>
          <span>密码</span>
          <input
            v-model="password"
            type="password"
            placeholder="至少 6 位"
            autocomplete="current-password"
          />
        </label>

        <p v-if="error" class="error">{{ error }}</p>

        <button type="submit" class="submit" :disabled="loading">
          {{ loading ? '请稍候…' : mode === 'login' ? '登 录' : '注 册' }}
        </button>
      </form>

      <p class="switch">
        {{ mode === 'login' ? '还没有账号?' : '已有账号?' }}
        <a href="#" @click.prevent="switchMode">
          {{ mode === 'login' ? '立即注册' : '去登录' }}
        </a>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: linear-gradient(135deg, #fbbf24 0%, #f97316 45%, #ea580c 100%);
}

.card {
  width: 100%;
  max-width: 400px;
  padding: 40px 36px 28px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 20px 60px rgba(124, 45, 18, 0.35);
}

.brand {
  text-align: center;
  margin-bottom: 28px;
}

.logo {
  font-size: 48px;
  line-height: 1;
}

.brand h1 {
  margin: 10px 0 4px;
  font-size: 32px;
  font-weight: 700;
  letter-spacing: 0.5px;
  background: linear-gradient(90deg, #f97316, #ea580c);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.tagline {
  margin: 0;
  font-size: 14px;
  color: #9ca3af;
}

.form label {
  display: block;
  margin-bottom: 16px;
}

.form label span {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #6b7280;
}

.form input {
  width: 100%;
  padding: 11px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  font-size: 15px;
  box-sizing: border-box;
  transition: border-color 0.15s;
}

.form input:focus {
  outline: none;
  border-color: #f97316;
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.12);
}

.error {
  margin: 0 0 12px;
  font-size: 13px;
  color: #dc2626;
}

.submit {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 4px;
  cursor: pointer;
  background: linear-gradient(90deg, #f97316, #ea580c);
  transition: opacity 0.15s, transform 0.05s;
}

.submit:hover:not(:disabled) {
  opacity: 0.92;
}

.submit:active:not(:disabled) {
  transform: scale(0.99);
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.switch {
  margin: 18px 0 0;
  text-align: center;
  font-size: 14px;
  color: #6b7280;
}

.switch a {
  color: #f97316;
  text-decoration: none;
  font-weight: 500;
}

.switch a:hover {
  text-decoration: underline;
}
</style>
