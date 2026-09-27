/**
 * SM3 杂凑算法（GB/T 32905-2016）—— 纯 JS 实现。
 *
 * 为什么要自己实现
 * ----------------
 * 浏览器**没有** SM3：WebCrypto 的 `crypto.subtle.digest` 只支持 SHA 系列。
 * 而 SM2 公钥解密必须用 SM3 做两件事：
 *   1. **KDF** —— 从共享点派生掩码去还原明文；
 *   2. **C3 完整性校验** —— 验证密文没被改过。
 * 没有 SM3，浏览器侧就无法在本地解开信封。
 *
 * 为什么不让服务端代解
 * --------------------
 * 那需要把用户的 `d_A` 发到服务端，直接放弃"服务端也解不开"这条保证
 * （计划 R1' 红线）。所以这一份实现是**必须**有的。
 *
 * 正确性保证
 * ----------
 * 由 `tools/verify-sm3-sm2-js.mjs` 用 **GB/T 32905-2016 标准向量**钉死：
 *   SM3("abc")  = 66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0
 *   SM3("abcd"×16) = debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732
 * 这两条与服务端（容器内 `cryptography` 的 SM3）结果一致，因此两侧可互验。
 */

/** 初始向量（GB/T 32905-2016 §4.1） */
const IV = new Uint32Array([
  0x7380166f, 0x4914b2b9, 0x172442d7, 0xda8a0600,
  0xa96f30bc, 0x163138aa, 0xe38dee4d, 0xb0fb0e4e
])

/** 32 位循环左移。用 >>> 0 保证结果是无符号 32 位，否则 JS 会按有符号处理而算错 */
function rotl(x, n) {
  return ((x << n) | (x >>> (32 - n))) >>> 0
}

/** 布尔函数 FF（j<16 为异或，否则为多数） */
function ff(j, x, y, z) {
  return j < 16 ? (x ^ y ^ z) >>> 0 : ((x & y) | (x & z) | (y & z)) >>> 0
}

/** 布尔函数 GG（j<16 为异或，否则为选择） */
function gg(j, x, y, z) {
  return j < 16 ? (x ^ y ^ z) >>> 0 : ((x & y) | (~x & z)) >>> 0
}

/** 置换函数 P0 */
function p0(x) {
  return (x ^ rotl(x, 9) ^ rotl(x, 17)) >>> 0
}

/** 置换函数 P1 */
function p1(x) {
  return (x ^ rotl(x, 15) ^ rotl(x, 23)) >>> 0
}

/**
 * 对一段字节做 SM3。
 *
 * @param {Uint8Array|number[]} input
 * @returns {Uint8Array} 32 字节摘要
 */
export function sm3(input) {
  const bytes = input instanceof Uint8Array ? input : Uint8Array.from(input)
  const bitLen = bytes.length * 8

  // ---- 填充：0x80 + 若干 0x00 + 64 位大端比特长度 ----
  // 长度编码里高 32 位用 Math.floor(bitLen / 2^32) —— 输入不可能到 512MB 以上，
  // 但写全了才符合规范
  const withPad = new Uint8Array((((bytes.length + 8) >> 6) + 1) << 6)
  withPad.set(bytes)
  withPad[bytes.length] = 0x80
  const view = new DataView(withPad.buffer)
  view.setUint32(withPad.length - 8, Math.floor(bitLen / 0x100000000), false)
  view.setUint32(withPad.length - 4, bitLen >>> 0, false)

  const v = new Uint32Array(IV)
  const w = new Uint32Array(68)
  const w1 = new Uint32Array(64)

  for (let block = 0; block < withPad.length; block += 64) {
    for (let i = 0; i < 16; i++) {
      w[i] = view.getUint32(block + i * 4, false)
    }
    for (let i = 16; i < 68; i++) {
      // W_j = P1(W_{j-16} ^ W_{j-9} ^ rotl(W_{j-3},15)) ^ rotl(W_{j-13},7) ^ W_{j-6}
      w[i] = (p1((w[i - 16] ^ w[i - 9] ^ rotl(w[i - 3], 15)) >>> 0) ^
        rotl(w[i - 13], 7) ^ w[i - 6]) >>> 0
    }
    for (let i = 0; i < 64; i++) {
      w1[i] = (w[i] ^ w[i + 4]) >>> 0
    }

    let [a, b, c, d, e, f, g, h] = v
    for (let j = 0; j < 64; j++) {
      // T_j：前 16 轮 0x79cc4519，之后 0x7a879d8a；注意按 j 取模 32 再循环左移
      const t = j < 16 ? 0x79cc4519 : 0x7a879d8a
      const ss1 = rotl((rotl(a, 12) + e + rotl(t, j % 32)) >>> 0, 7)
      const ss2 = (ss1 ^ rotl(a, 12)) >>> 0
      const tt1 = (ff(j, a, b, c) + d + ss2 + w1[j]) >>> 0
      const tt2 = (gg(j, e, f, g) + h + ss1 + w[j]) >>> 0
      d = c
      c = rotl(b, 9)
      b = a
      a = tt1
      h = g
      g = rotl(f, 19)
      f = e
      // E = P0(TT2)
      e = p0(tt2)
    }
    v[0] = (v[0] ^ a) >>> 0
    v[1] = (v[1] ^ b) >>> 0
    v[2] = (v[2] ^ c) >>> 0
    v[3] = (v[3] ^ d) >>> 0
    v[4] = (v[4] ^ e) >>> 0
    v[5] = (v[5] ^ f) >>> 0
    v[6] = (v[6] ^ g) >>> 0
    v[7] = (v[7] ^ h) >>> 0
  }

  const out = new Uint8Array(32)
  const outView = new DataView(out.buffer)
  for (let i = 0; i < 8; i++) {
    outView.setUint32(i * 4, v[i], false)
  }
  return out
}

/** 便捷封装：对多段字节按顺序做 SM3（等价于拼起来再算） */
export function sm3Concat(...parts) {
  let total = 0
  for (const part of parts) {
    total += part.length
  }
  const merged = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    merged.set(part, offset)
    offset += part.length
  }
  return sm3(merged)
}

/** 字节数组 → 小写十六进制 */
export function bytesToHex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** 十六进制 → 字节数组 */
export function hexToBytes(hex) {
  const text = String(hex).trim()
  if (text.length % 2 !== 0) {
    throw new Error('十六进制长度必须是偶数')
  }
  const out = new Uint8Array(text.length / 2)
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(text.substr(i * 2, 2), 16)
  }
  return out
}