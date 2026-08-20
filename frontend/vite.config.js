import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境把 /api 代理到 FastAPI 后端,前端代码里统一用相对路径请求。
// 后端端口默认 8000;被占用时用 VITE_API_TARGET 覆盖,
// 例如: VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
