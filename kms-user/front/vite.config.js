import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  base: process.env.NODE_ENV === 'production' ? '/user/' : '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5175,
    proxy: {
      '/generate-api': {
        target: 'http://localhost:9081',
        changeOrigin: true
      },
      '/lifecycle-api': {
        target: 'http://localhost:9082',
        changeOrigin: true
      },
      '/distribute-api': {
        target: 'http://localhost:8083',
        changeOrigin: true
      }
    }
  }
})
