import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  base: process.env.NODE_ENV === 'production' ? '/acceptance/' : '/',
  plugins: [vue()],
  resolve: {
    alias: {
      // 共享设计令牌包（仓库根目录 design-tokens/），5 个前端统一引用
      '@tokens': path.resolve(__dirname, '../../design-tokens')
    }
  },
  server: {
    port: 5176,
    proxy: {
      '/acceptance-api': {
        target: 'http://127.0.0.1:9090',
        changeOrigin: true
      }
    }
  }
})
