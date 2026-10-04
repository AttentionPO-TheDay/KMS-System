/**
 * `crystals-kyber` 的**严格模式**回归检查（浏览器打包专属缺陷的 Node 侧兜底）。
 *
 * 这个脚本防的是什么
 * ---------------
 * `crystals-kyber` 是 CommonJS 包、**非严格模式**，里面有两处靠隐式全局
 * "恰好能跑"的写法（顶层裸赋值函数、`for (i = …)` 裸变量循环）。
 * 打包成 ES 模块（恒严格模式）后它们才炸 —— 本仓库为此在
 * `vite/plugins/crystals-kyber-fix.js` 里做了补丁。
 *
 * ⚠️ **本仓库所有其它验收脚本都测不到这一类缺陷**：它们直接 import 源码
 *   在 Node 里跑，而 Node 对 CJS 走非严格路径 —— 同一个库、同一段代码，
 *   Node 里全绿、浏览器里全炸。KMS-005 的 Kyber 初始化与 2026-10-04 的
 *   "自检报 i is not defined"两次都是这么漏过去的。
 *
 * 检查方式
 * -------
 * 对三个实现文件各做一遍：
 *   1. 用**与构建同一份** transform（`vite/plugins/crystals-kyber-fix.js`，
 *      单一出处）打补丁；
 *   2. 把补丁后的代码放进 `vm` 的 **'use strict'** 上下文里执行
 *      —— 这正是浏览器 ESM 的处境；
 *   3. KeyGen → Encrypt → Decrypt 全跑，共享密钥必须**逐字节相同**。
 *
 * 判据是"补丁后三个变体全跑通"，不是"文件里没有裸赋值"：规则将来若被
 * 上游重写（不再匹配），这里会因为没有补丁而**真的炸**，而不是静默放行。
 *
 * 用法（在 kms-updatedel/front 下）：
 *     node tools/check-kyber-strict.mjs
 */
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import vm from 'node:vm'

import { fixCrystalsKyberStrictModeTransform } from '../vite/plugins/crystals-kyber-fix.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const require = createRequire(import.meta.url)
const VARIANTS = [512, 768, 1024]

let failed = 0

for (const variant of VARIANTS) {
  const sourcePath = join(HERE, '..', 'node_modules', 'crystals-kyber', `kyber${variant}.js`)
  const source = readFileSync(sourcePath, 'utf8')

  // 1) 与构建同一份 transform。stats 让"补了几处"可观察 ——
  //    补 0 处 = 上游换了写法，这条检查必须当失败处理（否则是在检查空气）。
  const patched = fixCrystalsKyberStrictModeTransform(source, sourcePath)
  if (!patched) {
    console.log(`[FAIL] kyber${variant}：transform 没命中任何补丁点 —— `
      + `上游可能改了写法，请复核 vite/plugins/crystals-kyber-fix.js 的规则`)
    failed += 1
    continue
  }
  if (patched.stats.forLoopPatched !== 1) {
    console.log(`[FAIL] kyber${variant}：期望补 1 处裸变量循环，实际 ${patched.stats.forLoopPatched} 处`)
    failed += 1
    continue
  }

  // 2) 严格模式执行（= 浏览器 ESM 的处境）。模块依赖按 front 的 node_modules 解析。
  const moduleShim = { exports: {} }
  try {
    vm.runInNewContext("'use strict';\n" + patched.code, {
      require,
      module: moduleShim,
      exports: moduleShim.exports,
      console,
      process,
      Buffer,
    })
  } catch (error) {
    console.log(`[FAIL] kyber${variant}：严格模式加载失败：${error.name}: ${error.message}`)
    failed += 1
    continue
  }

  // 3) 往返：KeyGen → Encrypt → Decrypt，共享密钥逐字节相同。
  const kyber = moduleShim.exports
  try {
    const [pk, sk] = kyber[`KeyGen${variant}`]()
    const [ct, ss1] = kyber[`Encrypt${variant}`](pk)
    const ss2 = kyber[`Decrypt${variant}`](ct, sk)
    const same = Buffer.from(ss1).equals(Buffer.from(ss2))
    if (!same) {
      console.log(`[FAIL] kyber${variant}：往返得到的共享密钥**不同**（补丁不该改变密码学行为）`)
      failed += 1
      continue
    }
    console.log(`[OK]   kyber${variant}：严格模式下 KeyGen/Encrypt/Decrypt 往返一致`
      + `（pk=${pk.length}B ct=${ct.length}B ss=${ss1.length}B 逐字节相同）`)
  } catch (error) {
    // 这正是 2026-10-04 用户报的形态：ReferenceError: i is not defined
    console.log(`[FAIL] kyber${variant}：严格模式下调用失败：${error.name}: ${error.message}`)
    failed += 1
  }
}

if (failed) {
  console.log(`\n== check-kyber-strict：${failed} 个变体未通过 ==`)
  process.exitCode = 1
} else {
  console.log('\n== check-kyber-strict：3 个变体全部通过 ==')
  console.log('（判据 = 打上补丁后在**严格模式**里跑通往返；Node 非严格路径测不到这类缺陷。）')
}