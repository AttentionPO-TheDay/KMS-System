/**
 * `crypto` 模块名的浏览器替身（Vite alias 用，见 `vite.config.js`）。
 *
 * 为什么需要
 * ----------
 * `crystals-kyber` 是 Node 向的包，它这样取安全随机数：
 *
 *     const webcrypto = require('crypto').webcrypto;   // kyber768.js:4
 *
 * 浏览器里没有名为 `crypto` 的**模块**，Vite 解析这行会直接失败。
 *
 * 为什么这是等价替换而不是绕过
 * ----------------------------
 * Node 的 `crypto.webcrypto` 与浏览器的 `globalThis.crypto` **是同一套
 * WebCrypto API**（同一份 W3C 规范，Node 15+ 起按规范实现）。
 * 该包用到的只有 `getRandomValues`，两边语义完全一致。
 *
 * ⚠️ 边界：本文件只替身**这一个模块名**。若日后引入别的 Node 向包、
 *    且它需要的是 `crypto` 的其它能力（如 `createHash`、文件流加密），
 *    这里会以"属性不存在"的明确方式失败 —— 而不是悄悄给出错误结果。
 *    那种情况应当换包，而不是往这里堆 Node API 的模拟实现。
 *
 * ⚠️ 与 `utils/sm3.js` 的关系：那个是本仓库自带的 SM3（浏览器不提供国密哈希），
 *    与本文件无关。这里只解决"模块名解析"，不引入任何密码算法。
 */

/**
 * `webcrypto` 属性 —— `crystals-kyber` 真正要的东西。
 *
 * 直接返回 `globalThis.crypto` 而非包装对象：包装一层会改变
 * `getRandomValues` 的调用上下文（`this`），在某些浏览器上会抛
 * `Illegal invocation`，而那种报错与"随机数不可用"看起来毫不相干。
 */
export const webcrypto = globalThis.crypto

export default { webcrypto }