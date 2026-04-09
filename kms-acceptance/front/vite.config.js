import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: process.env.NODE_ENV === 'production' ? '/acceptance/' : '/',
  plugins: [vue()],
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
