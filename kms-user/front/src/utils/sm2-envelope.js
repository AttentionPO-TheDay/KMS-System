/**
 * SM2 公钥解密的**浏览器侧**实现（GB/T 32918.4-2016）。
 *
 * 用途：在用户本机把分发过来的对称密钥信封解开。
 *
 * 为什么必须在浏览器里做
 * ----------------------
 * 信封是用用户的 `d_A` 对应的公钥点 `P_A` 加密的。要在服务端解开，
 * 就得把 `d_A` 发上去 —— 那等于放弃"服务端也解不开"这条保证（计划 R1' 红线）。
 * 所以解密只能在本机做，代价是必须自带 SM3（浏览器不提供）与椭圆曲线运算。
 *
 * 与服务端实现的关系
 * ------------------
 * 服务端那份（`pqkds/sm2_crypto.py`）已用**国标附录向量逐字节验证**并通过与
 * gmssl 的双向互通。本文件是它在浏览器侧的对应物，**用同一组国标向量验证**
 * （见 `tools/verify-sm3-sm2-js.mjs`），两边结果必须一致 —— 否则用户解不开服务端封的信封。
 *
 * 密文布局：`C1 || C3 || C2`
 *   C1 = 65 字节未压缩点（04||x||y）
 *   C3 = 32 字节 SM3 摘要，用于完整性校验
 *   C2 = 与明文等长的掩码后数据
 *
 * ⚠️ 关于曲线参数：**国标附录示例用的是它自己的一条测试曲线，不是生产用的 sm2p256v1**
 * （附录 p = 8542D69E…，生产 p = FFFFFFFE…）。因此曲线参数做成可注入的，
 * 测试用附录曲线跑国标向量，生产用默认的 sm2p256v1。
 */
// 显式写 `.js` 后缀：Vite 两种都接受，而 Node 的 ESM **必须**有后缀 ——
// 这样这份实现才能在 Node 里被 `tools/verify-sm3-sm2-js.mjs` 直接加载做国标向量验证。
import { sm3, sm3Concat, hexToBytes } from './sm3.js'

/** 生产曲线 sm2p256v1 —— 与 KMS 侧一致 */
export const SM2_P256 = {
  name: 'sm2p256v1',
  p: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF'),
  a: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC'),
  b: BigInt('0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93'),
  n: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123'),
  gx: BigInt('0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7'),
  gy: BigInt('0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0')
}

/** 完整性校验失败。与"格式错误"分开，让调用方能区分"被改过"与"文件不对" */
export class Sm2IntegrityError extends Error {
  constructor(message) {
    super(message)
    this.name = 'Sm2IntegrityError'
  }
}

const mod = (v, m) => ((v % m) + m) % m

function modInverse(a, m) {
  let [oldR, r] = [mod(a, m), m]
  let [oldS, s] = [1n, 0n]
  while (r !== 0n) {
    const q = oldR / r
    ;[oldR, r] = [r, oldR - q * r]
    ;[oldS, s] = [s, oldS - q * s]
  }
  if (oldR !== 1n) {
    throw new Error('模逆不存在（点可能重合）')
  }
  return mod(oldS, m)
}

/** 仿射点加；null 表示无穷远点 */
function pointAdd(p1, p2, curve) {
  if (p1 === null) return p2
  if (p2 === null) return p1
  const [x1, y1] = p1
  const [x2, y2] = p2
  let lambda
  if (x1 === x2 && mod(y1 + y2, curve.p) === 0n) {
    return null
  }
  if (x1 === x2 && y1 === y2) {
    lambda = mod((3n * x1 * x1 + curve.a) * modInverse(2n * y1, curve.p), curve.p)
  } else {
    lambda = mod((y2 - y1) * modInverse(x2 - x1, curve.p), curve.p)
  }
  const x3 = mod(lambda * lambda - x1 - x2, curve.p)
  return [x3, mod(lambda * (x1 - x3) - y1, curve.p)]
}

function pointMul(k, point, curve) {
  let result = null
  let addend = point
  let n = mod(k, curve.n)
  while (n > 0n) {
    if (n & 1n) result = pointAdd(result, addend, curve)
    addend = pointAdd(addend, addend, curve)
    n >>= 1n
  }
  return result
}

const to32 = (v) => {
  const hex = v.toString(16).padStart(64, '0')
  return hexToBytes(hex)
}

/**
 * SM2 的 KDF（GB/T 32918.4 §5.4.3）。
 *
 * 反复 `SM3(x2 || y2 || 计数器)` 并拼接，直到够长。计数器是 32 位大端，从 1 开始。
 */
function kdf(x2, y2, keyLen) {
  const x = to32(x2)
  const y = to32(y2)
  const out = new Uint8Array(keyLen)
  let offset = 0
  let counter = 1
  while (offset < keyLen) {
    const ct = new Uint8Array(4)
    new DataView(ct.buffer).setUint32(0, counter, false)
    const digest = sm3Concat(x, y, ct)
    const take = Math.min(digest.length, keyLen - offset)
    out.set(digest.subarray(0, take), offset)
    offset += take
    counter += 1
    if (counter > 0xffffffff) {
      throw new Error('KDF 计数器溢出')
    }
  }
  return out
}

/**
 * 判断一个点是否在指定曲线上（格式合法但不在曲线上的点必须被拒绝 ——
 * 否则会拿一个不存在的点去算，得到的"明文"是垃圾）。
 */
export function isValidPublicKey(publicKeyHex, curve = SM2_P256) {
  const hex = String(publicKeyHex || '').toLowerCase()
  if (!/^04[0-9a-f]{128}$/.test(hex)) {
    return false
  }
  const x = BigInt('0x' + hex.slice(2, 66))
  const y = BigInt('0x' + hex.slice(66, 130))
  if (x >= curve.p || y >= curve.p) {
    return false
  }
  // y² ≡ x³ + ax + b (mod p)
  return mod(y * y - (x * x * x + curve.a * x + curve.b), curve.p) === 0n
}

/**
 * 用私钥标量解开一个 SM2 信封。
 *
 * @param {object} envelope  形如 `{algorithm:'sm2', ciphertext:'<hex C1||C3||C2>', ...}`
 * @param {string} privateKeyHex  `d_A`，64 位十六进制
 * @param {object} [curve]  曲线参数（默认 sm2p256v1；测试注入国标附录曲线）
 * @returns {Uint8Array} 明文
 * @throws {Sm2IntegrityError} C3 校验失败（密文被改 / 私钥不对）
 */
export function decryptEnvelope(envelope, privateKeyHex, curve = SM2_P256) {
  if (!envelope || typeof envelope !== 'object') {
    throw new Error('信封格式错误：应为对象')
  }
  const algorithm = envelope.algorithm || 'sm2'
  if (algorithm !== 'sm2') {
    throw new Error(`信封的算法标记不是 sm2：${algorithm}`)
  }
  const ciphertextHex = String(envelope.ciphertext || '').toLowerCase()
  if (!/^[0-9a-f]+$/.test(ciphertextHex) || ciphertextHex.length < 130 + 64) {
    throw new Error('密文长度不足以包含 C1 与 C3')
  }

  const keyHex = String(privateKeyHex || '').trim().toLowerCase()
  if (!/^[0-9a-f]{64}$/.test(keyHex)) {
    throw new Error('私钥必须是 64 位十六进制')
  }
  const d = BigInt('0x' + keyHex)
  if (d <= 0n || d >= curve.n) {
    throw new Error('私钥不在 [1, n-1] 范围内')
  }

  const raw = hexToBytes(ciphertextHex)
  const c1 = raw.subarray(0, 65)
  const c3 = raw.subarray(65, 97)
  const c2 = raw.subarray(97)

  if (c1[0] !== 0x04) {
    throw new Error('C1 不是未压缩点（应以 04 开头）')
  }
  const x1 = BigInt('0x' + ciphertextHex.slice(2, 66))
  const y1 = BigInt('0x' + ciphertextHex.slice(66, 130))
  const point = [x1, y1]

  // [d]C1 —— 共享点。注意：即使 C1 不在曲线上也会算出"某个点"，
  // 所以这里显式校验，否则会静默算出一个错误结果（C3 大概率失败，但报错会很含糊）。
  if (!isValidPublicKey('04' + ciphertextHex.slice(2, 130), curve)) {
    throw new Error('C1 不在曲线上')
  }
  const shared = pointMul(d, point, curve)
  if (shared === null) {
    throw new Error('共享点为无穷远点，C1 非法')
  }
  const [x2, y2] = shared

  // 明文 = C2 ⊕ KDF(x2||y2, len)
  const mask = kdf(x2, y2, c2.length)
  const plain = new Uint8Array(c2.length)
  for (let i = 0; i < c2.length; i++) {
    plain[i] = c2[i] ^ mask[i]
  }

  // C3 = SM3(x2 || M || y2) —— 必须校验，否则"解出来的"可能只是垃圾
  const expectC3 = sm3Concat(to32(x2), plain, to32(y2))
  let diff = 0
  for (let i = 0; i < 32; i++) {
    diff |= expectC3[i] ^ c3[i]
  }
  if (diff !== 0) {
    throw new Sm2IntegrityError(
      'SM2 完整性校验失败：密文可能被改动，或这份信封不是用该私钥对应的公钥加密的'
    )
  }
  return plain
}

/** 十六进制字符串形式的明文（对称密钥就是 32 位十六进制） */
export function decryptToHex(envelope, privateKeyHex, curve = SM2_P256) {
  const bytes = decryptEnvelope(envelope, privateKeyHex, curve)
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
}