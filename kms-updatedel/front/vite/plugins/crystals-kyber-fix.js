/**
 * 修 `crystals-kyber` 的**严格模式**问题（浏览器打包专属）。
 *
 * 这个文件为什么单独存在
 * --------------------
 * 规则必须**单一出处**：构建（`vite.config.js`）与回归检查
 * （`tools/check-kyber-strict.mjs`）用的是同一份 transform ——
 * 两处各抄一道正则，迟早只改一处，而漂移的表现是"检查脚本说修好了、
 * 打包产物里却没修"（或反过来），两边都要重新排查一遍。
 *
 * 问题
 * ----
 * 该包的 `kyber512/768/1024.js` 里有两处**同类**缺陷，都只在打包成
 * ES 模块（恒严格模式）后才现形 —— CommonJS 下靠隐式全局"恰好能跑"：
 *
 *  ① 顶层裸赋值定义函数：
 *
 *         KeyGen512 = function() { ... }     // 没有 var/let/const
 *
 *  ② `indcpa_enc` 里的裸变量循环（**2026-10-04 追加修复**）：
 *
 *         let u = new Array(paramsK);
 *         for (i = 0; i < paramsK; i++) { ... }   // 上面的 let i 是块级，出了循环就没了
 *
 *     ② 没有被 ① 的正则覆盖（那是行首函数赋值），于是节点端「Kyber 密钥的
 *     自检按钮」报 `i is not defined` —— 而这条路径 **KeyGen 不经过、
 *     Encrypt 才经过**：生成密钥一路正常（节点初始化能过），
 *     只有自检/封装的封装（`encapsulate`）才炸，报错与"密钥材料坏了"混在一起。
 *
 * 症状（2026-09-30 与 2026-10-04 各实测一次）
 * -----------------------------------------
 * 构建**成功**、页面也打得开，只有真正用到对应函数时才炸：
 *   * ①：节点首次初始化走到「正在生成 Kyber…」就失败，节点永远停在
 *     PENDING_INIT，报错是一句 `KeyGen512 is not defined`；
 *   * ②：生成/初始化都正常，点「自检」报 `i is not defined`。
 * 两者都是懒加载 chunk，错在调用时而非加载时。
 *
 * ⚠️ 这一类缺陷**Node 侧回归脚本永远测不到**（Node 走 CJS、非严格），
 *    必须由 `tools/check-kyber-strict.mjs` 的严格模式检查兜住 ——
 *    它和本模块共用同一份 transform。
 *
 * 修法
 * ----
 * ①：给 12 处顶层赋值补 `var `；
 * ②：把 `for (i = ` 改成 `for (var i = `（三个文件各一处）。
 *    ⚠️ 必须是 `var` 而不是 `let i`：循环**之后**同函数里还有 `u[i] = …`
 *    依赖这个 `i` 存续（隐式全局在 sloppy 下的行为就是"函数内可见"），
 *    `let` 会把它掐掉、在下一处 use 直接报错。`var` 与原语义逐点等价。
 * 两者都只补声明、算法实现一字未改 —— 改后已实测三个变体的
 * KeyGen→Encrypt→Decrypt 往返共享密钥与服务端 .so **逐字节相同**。
 *
 * 为什么用插件而不是改 node_modules
 * --------------------------------
 * 改 node_modules 在 `npm ci` 后就没了，且改动不进版本库 —— 会变成
 * "本地能跑、别人拉下来就坏"的隐形状态。插件随构建配置一起进版本库，可复现。
 */

/** 只命中该包的三个实现文件（按路径分段匹配，避免误伤同名文件）。 */
export const CRYSTALS_KYBER_TARGET = /[\\/]crystals-kyber[\\/]kyber(512|768|1024)\.js$/

/**
 * 对单个模块做两处补丁；不需要改就返回 `null`（与 Vite transform 约定一致）。
 * `id` 用来判断是否为目标文件 —— 非目标文件一律不动。
 */
export function fixCrystalsKyberStrictModeTransform(code, id) {
  if (!CRYSTALS_KYBER_TARGET.test(id)) return null

  // ① 只匹配**行首**（`^` + `m`）= 顶层赋值。
  //    已带 `var ` 的行不会被匹配：`var` 之后跟的是空格+标识符，
  //    而不是 ` = function`。
  let fixed = code.replace(/^([A-Za-z_$][A-Za-z0-9_$]*)(\s*=\s*function)/gm, 'var $1$2')
  // ② 裸变量循环（见文件头 ② 的完整说明）。
  const beforeLoop = fixed
  fixed = fixed.replace(/for \(i = /g, 'for (var i = ')
  if (fixed === code) return null
  return {
    code: fixed,
    map: null,
    // 诊断口径（检查脚本与构建日志都用它）：补了几处、补的是什么 ——
    // 补 0 处 = 上游换了写法、这两条规则需要复核。
    stats: {
      forLoopPatched: (beforeLoop.match(/for \(i = /g) || []).length,
      changed: true,
    },
  }
}

/** Vite 插件外壳。`enforce: 'pre'` 的理由见下。 */
export default function fixCrystalsKyberStrictMode() {
  return {
    name: 'fix-crystals-kyber-strict-mode',
    // 必须在 commonjs 插件**之前**跑：等它转完，裸赋值已经被搬进
    // ESM 包装里，行首匹配就对不上了。
    enforce: 'pre',
    transform(code, id) {
      const result = fixCrystalsKyberStrictModeTransform(code, id)
      if (!result) return null
      if (process.env.KMS_DEBUG_KYBER_PATCH) {
        console.log('[fix-crystals-kyber-strict-mode]', id,
          'for-i:', result.stats.forLoopPatched, '处')
      }
      return { code: result.code, map: null }
    },
  }
}