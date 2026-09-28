/**
 * `fs` 的浏览器替身（Vite alias 用，见 `vite.config.js`）。
 *
 * 为什么会有这个文件
 * ------------------
 * `crystals-kyber` 的 `kyber*.js` 里有一处 `require('fs')`，但**只在它的
 * 自测函数 `Test512/768/1024` 里**，用途是读取 KAT 向量文件
 * （`PQCkemKAT_2400.rsp`）来做标准向量自检。
 *
 * 本系统只用 `KeyGen*` / `Encrypt*` / `Decrypt*`，**从不调用 `Test*`**，
 * 所以这个替身在正常运行中永远不会被执行 —— 它存在只是为了**让打包器能解析**。
 *
 * ⚠️ 它刻意**抛错而不是返回空对象**。
 *    如果哪天有人真的调到 `Test*`，应当立刻看到"浏览器里没有文件系统"，
 *    而不是拿到一个空结果、把"自测没跑"误当成"自测通过"。
 *    这与本仓库一贯的做法一致：宁可明确失败，也不要静默给出错误的成功。
 */

function unavailable(name) {
  return () => {
    throw new Error(
      `浏览器环境没有 fs.${name}。本替身只为打包解析存在（见 utils/crypto/node-fs-stub.js）—— ` +
        '若你正试图运行 crystals-kyber 的 Test* 自测函数，那是 Node 专用路径，' +
        '应在 Node 里跑，不要放进浏览器。'
    )
  }
}

export const readFileSync = unavailable('readFileSync')
export const writeFileSync = unavailable('writeFileSync')
export const existsSync = unavailable('existsSync')

export default { readFileSync, writeFileSync, existsSync }