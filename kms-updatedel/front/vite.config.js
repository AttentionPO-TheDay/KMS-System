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
    base: isProduction ? '/lifecycle/' : '/',
    plugins: createVitePlugins(env, command === 'build'),
    resolve: {
      // https://cn.vitejs.dev/config/#resolve-alias
      alias: {
        // 设置路径
        '~': path.resolve(__dirname, './'),
        // 设置别名
        '@': path.resolve(__dirname, './src')
      },
      // https://cn.vitejs.dev/config/#resolve-extensions
      extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
    },
    // vite 相关配置
    server: {
      port: 5174,
      host: true,
      open: true,
      proxy: {
        // https://cn.vitejs.dev/config/#server-proxy
        // 生命周期系统API代理
        '/lifecycle-api': {
          target: 'http://localhost:9082',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/lifecycle-api/, '')
        },
        // 权限系统API代理
        '/permission-api': {
          target: 'http://localhost:9082',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/permission-api/, '')
        },
        // 开发代理
        '/dev-api': {
          target: 'http://localhost:80',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/dev-api/, '')
        }
      }
    },
    //fix:error:stdin>:7356:1: warning: "@charset" must be the first rule in the file
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
