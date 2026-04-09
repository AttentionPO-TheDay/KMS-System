import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import createVitePlugins from './vite/plugins'

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd())
  const { VITE_APP_ENV } = env
  const isProduction = command === 'build' && VITE_APP_ENV === 'production'
  return {
    // 部署生产环境和开发环境下的URL。
    base: isProduction ? '/distribute/' : '/',
    plugins: createVitePlugins(env, command === 'build'),
    resolve: {
      alias: {
        '~': path.resolve(__dirname, './'),
        '@': path.resolve(__dirname, './src')
      },
      extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
    },
    server: {
      port: 5175,
      host: true,
      open: true,
      proxy: {
        '/distribute-api': {
          target: 'http://localhost:8083',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/distribute-api/, '')
        },
        '/dev-api': {
          target: 'http://localhost:80',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/dev-api/, '')
        }
      }
    },
    css: {
      postcss: {
        plugins: [
          {
            postcssPlugin: 'internal:charset-removal',
            AtRule: {
              charset: (atRule) => {
                if (atRule.name === 'charset') {
                  atRule.remove();
                }
              }
            }
          }
        ]
      }
    }
  }
})
