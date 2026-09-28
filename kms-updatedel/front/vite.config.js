import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import createVitePlugins from './vite/plugins'

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd())
  const { VITE_APP_ENV } = env
  return {
    // 部署生产环境和开发环境下的URL。
    // 默认情况下，vite 会假设你的应用是被部署在一个域名的根路径上
    // 例如 https://www.ruoyi.vip/。如果应用被部署在一个子路径上，你就需要用这个选项指定这个子路径。例如，如果你的应用被部署在 https://www.ruoyi.vip/admin/，则设置 baseUrl 为 /admin/。
    base: VITE_APP_ENV === 'production' ? '/updatedel/' : '/',
    plugins: createVitePlugins(env, command === 'build'),
    resolve: {
      // https://cn.vitejs.dev/config/#resolve-alias
      alias: {
        // 设置路径
        '~': path.resolve(__dirname, './'),
        // 设置别名
        '@': path.resolve(__dirname, './src'),
        // 共享设计令牌包（仓库根目录 design-tokens/），5 个前端统一引用
        '@tokens': path.resolve(__dirname, '../../design-tokens'),
        // -------------------------------------------------------------------
        // `crystals-kyber` 是 Node 向的包：它 `require('crypto').webcrypto`
        // 来拿安全随机数（`kyber768.js:4`）。浏览器里没有 `crypto` 模块，
        // 不打这个补丁，Vite 构建会在解析时失败。
        //
        // 映射到 `webcrypto-shim.js` 是**语义等价**的替换，不是绕过：
        // Node 的 `crypto.webcrypto` 与浏览器的 `globalThis.crypto`
        // 本来就是同一套 WebCrypto API（同一份规范），
        // 该包用到的只有 `getRandomValues`。
        //
        // ⚠️ 只映射到 `crypto` 这个**模块名**，不影响 node 内置模块的其它用法；
        //    且仅对该包生效（见下方 optimizeDeps 的说明）。
        // -------------------------------------------------------------------
        crypto: path.resolve(__dirname, './src/utils/crypto/webcrypto-shim.js'),
        // -------------------------------------------------------------------
        // `crystals-kyber` 的 kyber*.js 里还有一处 `require('fs')`，但它**只在
        // 自测函数 `Test*` 里**（读 KAT 向量文件）。本系统只用 KeyGen/Encrypt/Decrypt，
        // 从不调 Test* —— 替身只为让打包器能解析，运行期不会被执行。
        //
        // ⚠️ 替身**抛错而不是返回空对象**：万一有人真调到了 Test*，
        //    应当立刻看到"浏览器没有文件系统"，而不是把"自测没跑"当成"自测通过"。
        // -------------------------------------------------------------------
        fs: path.resolve(__dirname, './src/utils/crypto/node-fs-stub.js')
      },
      // https://cn.vitejs.dev/config/#resolve-extensions
      extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
    },
    // vite 相关配置
    server: {
      // 端口分配（避免与其它前端 dev server 冲突，可同时启动联调）：
      //   kms-user 81 / kms-generate 82 / kms-updatedel 83 / kms-acceptance 5176
      // 历史上三者均使用 81，无法同时运行。
      port: 83,
      host: true,
      open: true,
      proxy: {
        // https://cn.vitejs.dev/config/#server-proxy
        '/generate-api': {
          target: 'http://localhost:9081',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/generate-api/, '')
        },
        '/lifecycle-api': {
          target: 'http://localhost:9082',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/lifecycle-api/, '')
        },
        // 分发模块（Django）走网关的 /pqkds-api/，见 §5.1。
        // 阶段 1 从 kms-user 一并迁入（分发页现由本控制台承载），
        // 因此这里必须补上，否则联调时分发页会打到 SPA fallback 拿到 HTML。
        '/pqkds-api': {
          target: 'http://localhost:8001',
          changeOrigin: true
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
