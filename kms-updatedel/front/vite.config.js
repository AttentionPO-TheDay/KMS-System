import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import createVitePlugins from './vite/plugins'

/**
 * 修 `crystals-kyber` 的**严格模式**问题（浏览器打包专属）。
 *
 * 问题
 * ----
 * 该包的 `kyber512/768/1024.js` 用**裸赋值**定义四个函数：
 *
 *     KeyGen512 = function() { ... }     // 没有 var/let/const
 *
 * 这在 CommonJS 下能跑 —— CJS **不是**严格模式，裸赋值会创建隐式全局变量。
 * （所以它的自测在 Node 里一直是好的，问题不会在那里暴露。）
 *
 * 但打包成 ES 模块后是**严格模式**：对未声明标识符赋值会直接抛
 * `ReferenceError: KeyGen512 is not defined`。
 *
 * 症状（2026-09-30 实测）
 * ----------------------
 * 构建**成功**、页面也打得开，只有真正用到 Kyber 时才炸：
 * 节点首次初始化走到「正在生成 Kyber…」就失败，节点永远停在 PENDING_INIT，
 * 而报错只有一句 `KeyGen512 is not defined`，完全看不出是这个包的问题。
 * （它是懒加载 chunk，所以错在调用时而非加载时。）
 *
 * 修法
 * ----
 * 给这 12 处补上 `var `：语义与原隐式全局一致，但在模块作用域内、且合法。
 * **只动这一处**，算法实现一字未改。
 *
 * 为什么用插件而不是改 node_modules
 * --------------------------------
 * 改 node_modules 在 `npm ci` 后就没了，且改动不进版本库 —— 会变成
 * "本地能跑、别人拉下来就坏"的隐形状态。插件随构建配置一起进版本库，可复现。
 *
 * 定位与下方 alias 里的 crypto shim / fs stub 一致：都是
 * "让这个 Node 向的包能在浏览器里跑"，不改变它的密码学行为。
 */
function fixCrystalsKyberStrictMode() {
  // 只命中该包的三个实现文件（按路径分段匹配，避免误伤同名文件）
  const TARGET = /[\\/]crystals-kyber[\\/]kyber(512|768|1024)\.js$/
  return {
    name: 'fix-crystals-kyber-strict-mode',
    // 必须在 commonjs 插件**之前**跑：等它转完，裸赋值已经被搬进
    // ESM 包装里，行首匹配就对不上了。
    enforce: 'pre',
    transform(code, id) {
      if (!TARGET.test(id)) return null
      // 只匹配**行首**（`^` + `m`）= 顶层赋值。
      // 已带 `var ` 的行不会被匹配：`var` 之后跟的是空格+标识符，
      // 而不是 ` = function`。
      const fixed = code.replace(/^([A-Za-z_$][A-Za-z0-9_$]*)(\s*=\s*function)/gm, 'var $1$2')
      if (fixed === code) return null
      return { code: fixed, map: null }
    },
  }
}

/**
 * 给 `crystals-kyber` 补上 `Buffer` 全局（浏览器打包专属）。
 *
 * 为什么需要
 * ----------
 * 修好严格模式后，它的下一步报错是 `Buffer is not defined`：
 * `kyber*.js` 里用了 `Buffer.from` / `Buffer.alloc` 各几十处，
 * 而 `Buffer` 是 **Node 的全局变量**，浏览器没有。
 *
 * ⚠️ 与 `crypto` / `fs` 那两个坑**不同**：那两个是模块名，可以用 alias
 *    换掉；`Buffer` 是全局标识符，alias 治不了，只能在模块作用域里注入。
 *
 * 为什么注入**真正的 `buffer` 包**而不是手写 polyfill
 * --------------------------------------------------
 * 这段代码是 Kyber 的字节级实现，其共享密钥已与服务端 `.so` **逐字节比对过**
 * （见 `utils/crypto/browser-provider.js` 顶部注释）。手写 polyfill 只要在
 * 边界情形上有一处偏差，就会让这条已验证的等价性失效 ——
 * 而那种偏差不会报错，只会让分发出来的密钥在某些输入下对不上。
 * `buffer` 是 Node 官方同源实现，行为一致，风险最低。
 *
 * 为什么限定在这三个文件里注入
 * --------------------------
 * 全局注入会悄悄替掉应用别处对 `Buffer` 的引用，让人误以为浏览器原生支持它。
 * 只在这三个文件里注入，作用域清楚，也不会掩盖其它包对 Node API 的依赖
 * ——那种依赖应该像这里一样被**显式**处理。
 *
 * 为什么显式加依赖：`buffer@5.7.1` 当前是某个传递依赖带进来的，直接 import
 * 它属于"用了没声明的依赖"，换一次 lockfile 就可能消失。
 */
function provideBufferForCrystalsKyber() {
  const TARGET = /[\\/]crystals-kyber[\\/]kyber(512|768|1024)\.js$/
  return {
    name: 'provide-buffer-for-crystals-kyber',
    enforce: 'pre',
    transform(code, id) {
      if (!TARGET.test(id)) return null
      if (!/\bBuffer\b/.test(code)) return null
      return {
        // 在文件最前面引入并绑定到局部 `Buffer`。只加一行、不动任何原有代码
        // —— 这段密码学实现要保持原样。
        //
        // ⚠️ 必须用 `require(...)` 而**不是** `import ... from`（2026-09-30 实测踩到）：
        //    这个包是 CommonJS，文件里本来全是 `require(...)` + `exports.x = ...`，
        //    由打包器的 commonjs 插件统一转成 ESM。
        //    一旦插进去一条真正的 `import` 语句，文件就变成"既有 import 又有 require"
        //    的混合体，commonjs 插件会**放弃转换**，把剩下的 `require(...)` 原样留在
        //    产物里 —— 报错就成了 `require is not defined`，
        //    而它看起来像是"这个包不支持浏览器"，其实是我注入方式破坏了模块格式。
        //    用 require 注入则与文件原有写法一致，走同一条转换路径。
        code: `const { Buffer } = require('buffer');\n${code}`,
        map: null,
      }
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd())
  const { VITE_APP_ENV } = env
  return {
    // 部署生产环境和开发环境下的URL。
    // 默认情况下，vite 会假设你的应用是被部署在一个域名的根路径上
    // 例如 https://www.ruoyi.vip/。如果应用被部署在一个子路径上，你就需要用这个选项指定这个子路径。例如，如果你的应用被部署在 https://www.ruoyi.vip/admin/，则设置 baseUrl 为 /admin/。
    base: VITE_APP_ENV === 'production' ? '/updatedel/' : '/',
    plugins: [fixCrystalsKyberStrictMode(), provideBufferForCrystalsKyber(), ...createVitePlugins(env, command === 'build')],
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
