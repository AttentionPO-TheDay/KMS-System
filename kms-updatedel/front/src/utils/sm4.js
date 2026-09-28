/**
 * SM4-GCM 的**浏览器侧**实现（GB/T 32907-2016 + GCM）。
 *
 * 为什么需要自己写
 * ----------------
 * 节点腿信封的载荷层是 **SM4-GCM**（服务端 `sm4_crypto.py:138`
 * 用的是 pycryptodome 的 `modes.GCM`），浏览器要解开它就必须有 SM4-GCM。
 * 而现成的 JS 库都不提供这个组合：
 *   * `gm-crypto`（本仓库已在用）的 SM4 **只有 ECB / CBC**；
 *   * `sm-crypto` 的 SM4 同样**不支持 GCM**；
 *   * `@noble/ciphers` 只有 AES / ChaCha 系，没有 SM4。
 * 这与 `utils/sm3.js` 是同一个处境（浏览器不提供国密算法），
 * 所以照同样的办法处理：**自己实现 + 用国标向量钉死**。
 *
 * 判据（两者缺一不可）
 * --------------------
 * 1. **GB/T 32907-2016 附录 A 的标准向量**：单分组加密
 *    key/plain = `0123456789abcdeffedcba9876543210`
 *    cipher    = `681edf34d206965e86b3e94f536e4246`
 * 2. **与服务端 `SM4Crypto` 逐字节对打** —— 这一条才是真正的判据：
 *    向量只能证明"我实现的是 SM4"，对打才能证明"两边是同一套封装"。
 *
 * ⚠️ 与 SM3 那次的教训一致：自洽的往返测试**证明不了任何事** ——
 *    一个完全错误的实现也能往返一致。
 */
import { sm3 } from './sm3.js'

// ---------------------------------------------------------------------------
// SM4 分组密码（GB/T 32907-2016）
// ---------------------------------------------------------------------------
//: S 盒。**必须逐字节写死** —— 它没有生成公式，是国标直接给出的置换表。
const SBOX = new Uint8Array([
  0xd6, 0x90, 0xe9, 0xfe, 0xcc, 0xe1, 0x3d, 0xb7, 0x16, 0xb6, 0x14, 0xc2, 0x28, 0xfb, 0x2c, 0x05,
  0x2b, 0x67, 0x9a, 0x76, 0x2a, 0xbe, 0x04, 0xc3, 0xaa, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
  0x9c, 0x42, 0x50, 0xf4, 0x91, 0xef, 0x98, 0x7a, 0x33, 0x54, 0x0b, 0x43, 0xed, 0xcf, 0xac, 0x62,
  0xe4, 0xb3, 0x1c, 0xa9, 0xc9, 0x08, 0xe8, 0x95, 0x80, 0xdf, 0x94, 0xfa, 0x75, 0x8f, 0x3f, 0xa6,
  0x47, 0x07, 0xa7, 0xfc, 0xf3, 0x73, 0x17, 0xba, 0x83, 0x59, 0x3c, 0x19, 0xe6, 0x85, 0x4f, 0xa8,
  0x68, 0x6b, 0x81, 0xb2, 0x71, 0x64, 0xda, 0x8b, 0xf8, 0xeb, 0x0f, 0x4b, 0x70, 0x56, 0x9d, 0x35,
  0x1e, 0x24, 0x0e, 0x5e, 0x63, 0x58, 0xd1, 0xa2, 0x25, 0x22, 0x7c, 0x3b, 0x01, 0x21, 0x78, 0x87,
  0xd4, 0x00, 0x46, 0x57, 0x9f, 0xd3, 0x27, 0x52, 0x4c, 0x36, 0x02, 0xe7, 0xa0, 0xc4, 0xc8, 0x9e,
  0xea, 0xbf, 0x8a, 0xd2, 0x40, 0xc7, 0x38, 0xb5, 0xa3, 0xf7, 0xf2, 0xce, 0xf9, 0x61, 0x15, 0xa1,
  0xe0, 0xae, 0x5d, 0xa4, 0x9b, 0x34, 0x1a, 0x55, 0xad, 0x93, 0x32, 0x30, 0xf5, 0x8c, 0xb1, 0xe3,
  0x1d, 0xf6, 0xe2, 0x2e, 0x82, 0x66, 0xca, 0x60, 0xc0, 0x29, 0x23, 0xab, 0x0d, 0x53, 0x4e, 0x6f,
  0xd5, 0xdb, 0x37, 0x45, 0xde, 0xfd, 0x8e, 0x2f, 0x03, 0xff, 0x6a, 0x72, 0x6d, 0x6c, 0x5b, 0x51,
  0x8d, 0x1b, 0xaf, 0x92, 0xbb, 0xdd, 0xbc, 0x7f, 0x11, 0xd9, 0x5c, 0x41, 0x1f, 0x10, 0x5a, 0xd8,
  0x0a, 0xc1, 0x31, 0x88, 0xa5, 0xcd, 0x7b, 0xbd, 0x2d, 0x74, 0xd0, 0x12, 0xb8, 0xe5, 0xb4, 0xb0,
  0x89, 0x69, 0x97, 0x4a, 0x0c, 0x96, 0x77, 0x7e, 0x65, 0xb9, 0xf1, 0x09, 0xc5, 0x6e, 0xc6, 0x84,
  0x18, 0xf0, 0x7d, 0xec, 0x3a, 0xdc, 0x4d, 0x20, 0x79, 0xee, 0x5f, 0x3e, 0xd7, 0xcb, 0x39, 0x48
])

const FK = [0xa3b1bac6, 0x56aa3350, 0x677d9197, 0xb27022dc]

//: 系统参数 CK_i = (ck_{i,0} || ck_{i,1} || ck_{i,2} || ck_{i,3})，
//: 其中 ck_{i,j} = (4i + j) × 7 mod 256。用公式生成而不是抄 32 个常量 ——
//: 抄写是最容易错一位、而错了只表现为"解出来是乱码"的地方。
const CK = (() => {
  const out = new Uint32Array(32)
  for (let i = 0; i < 32; i++) {
    let v = 0
    for (let j = 0; j < 4; j++) {
      v = (v << 8) | (((4 * i + j) * 7) % 256)
    }
    out[i] = v >>> 0
  }
  return out
})()

const rotl = (x, n) => ((x << n) | (x >>> (32 - n))) >>> 0

/** 轮函数里的 τ（S 盒）+ L 线性变换 */
function tau(x) {
  return (
    ((SBOX[(x >>> 24) & 0xff] << 24) |
      (SBOX[(x >>> 16) & 0xff] << 16) |
      (SBOX[(x >>> 8) & 0xff] << 8) |
      SBOX[x & 0xff]) >>>
    0
  )
}

function tTransform(x) {
  const b = tau(x)
  return (b ^ rotl(b, 2) ^ rotl(b, 10) ^ rotl(b, 18) ^ rotl(b, 24)) >>> 0
}

/** T'（密钥扩展用）：与 T 相同，但线性变换换成 L'(b)=b⊕(b<<<13)⊕(b<<<23) */
function tPrime(x) {
  const b = tau(x)
  return (b ^ rotl(b, 13) ^ rotl(b, 23)) >>> 0
}

function expandKey(key) {
  if (key.length !== 16) {
    throw new Error(`SM4 密钥必须是 16 字节，收到 ${key.length}`)
  }
  const k = new Uint32Array(36)
  for (let i = 0; i < 4; i++) {
    k[i] = (((key[4 * i] << 24) | (key[4 * i + 1] << 16) | (key[4 * i + 2] << 8) | key[4 * i + 3]) ^ FK[i]) >>> 0
  }
  const rk = new Uint32Array(32)
  for (let i = 0; i < 32; i++) {
    k[i + 4] = (k[i] ^ tPrime((k[i + 1] ^ k[i + 2] ^ k[i + 3] ^ CK[i]) >>> 0)) >>> 0
    rk[i] = k[i + 4]
  }
  return rk
}

const readWord = (block, i) => ((block[4 * i] << 24) | (block[4 * i + 1] << 16) | (block[4 * i + 2] << 8) | block[4 * i + 3]) >>> 0

function writeWord(out, i, v) {
  out[4 * i] = (v >>> 24) & 0xff
  out[4 * i + 1] = (v >>> 16) & 0xff
  out[4 * i + 2] = (v >>> 8) & 0xff
  out[4 * i + 3] = v & 0xff
}

/**
 * 单分组加密/解密（16 字节进、16 字节出）。
 *
 * ⚠️ `rk` 必须由**同一次** `expandKey` 的调用者复用：
 *    本函数在 CTR/GCM 里会被调用成千上万次，每次重算轮密钥是纯浪费，
 *    而那种浪费不会报错，只会让大文件解密慢到看不出原因。
 */
function encryptBlock(rk, input, inOff, output, outOff) {
  const x = new Uint32Array(36)
  for (let i = 0; i < 4; i++) {
    x[i] = ((input[inOff + 4 * i] << 24) | (input[inOff + 4 * i + 1] << 16) |
      (input[inOff + 4 * i + 2] << 8) | input[inOff + 4 * i + 3]) >>> 0
  }
  for (let i = 0; i < 32; i++) {
    x[i + 4] = (x[i] ^ tTransform((x[i + 1] ^ x[i + 2] ^ x[i + 3] ^ rk[i]) >>> 0)) >>> 0
  }
  // 反序变换 R
  writeWord(output, outOff / 4, x[35])
  writeWord(output, outOff / 4 + 1, x[34])
  writeWord(output, outOff / 4 + 2, x[33])
  writeWord(output, outOff / 4 + 3, x[32])
}

function decryptBlock(rk, input, inOff, output, outOff) {
  const x = new Uint32Array(36)
  for (let i = 0; i < 4; i++) {
    x[i] = ((input[inOff + 4 * i] << 24) | (input[inOff + 4 * i + 1] << 16) |
      (input[inOff + 4 * i + 2] << 8) | input[inOff + 4 * i + 3]) >>> 0
  }
  // 解密就是把轮密钥**倒序**使用 —— 无需另一套轮函数
  for (let i = 0; i < 32; i++) {
    x[i + 4] = (x[i] ^ tTransform((x[i + 1] ^ x[i + 2] ^ x[i + 3] ^ rk[31 - i]) >>> 0)) >>> 0
  }
  writeWord(output, outOff / 4, x[35])
  writeWord(output, outOff / 4 + 1, x[34])
  writeWord(output, outOff / 4 + 2, x[33])
  writeWord(output, outOff / 4 + 3, x[32])
}

// ---------------------------------------------------------------------------
// GCM 模式（NIST SP 800-38D 的通用构造，作用在 SM4 之上）
// ---------------------------------------------------------------------------
/** GF(2^128) 乘法，按 SP 800-38D 的位序约定 */
function gfMul(x, y) {
  let z = new Uint32Array(4)
  let v = Uint32Array.from(y)
  for (let i = 0; i < 128; i++) {
    // 取 x 的第 i 位（**大端位序**：第 0 位是最高位）
    if ((x[(i / 32) | 0] >>> (31 - (i % 32))) & 1) {
      for (let j = 0; j < 4; j++) {
        z[j] ^= v[j]
      }
    }
    const lsb = v[3] & 1
    // v >>= 1（大端）
    v[3] = ((v[3] >>> 1) | (v[2] << 31)) >>> 0
    v[2] = ((v[2] >>> 1) | (v[1] << 31)) >>> 0
    v[1] = ((v[1] >>> 1) | (v[0] << 31)) >>> 0
    v[0] = v[0] >>> 1
    if (lsb) {
      v[0] ^= 0xe1000000
    }
  }
  return z
}

function ghash(h, aad, ciphertext) {
  const y = new Uint32Array(4)
  const absorb = (bytes) => {
    for (let off = 0; off < bytes.length; off += 16) {
      const block = new Uint32Array(4)
      for (let i = 0; i < 16 && off + i < bytes.length; i++) {
        block[(i / 4) | 0] ^= bytes[off + i] << (24 - 8 * (i % 4))
      }
      for (let i = 0; i < 4; i++) {
        y[i] ^= block[i]
      }
      const next = gfMul(y, h)
      y.set(next)
    }
  }
  absorb(aad)
  absorb(ciphertext)
  // 长度块：bitlen(aad) || bitlen(ciphertext)，各 64 位大端
  const lenBlock = new Uint32Array(4)
  lenBlock[1] = (aad.length * 8) >>> 0
  lenBlock[3] = (ciphertext.length * 8) >>> 0
  for (let i = 0; i < 4; i++) {
    y[i] ^= lenBlock[i]
  }
  return gfMul(y, h)
}

function inc32(counter) {
  // 只递增最后 32 位，且**不回卷到前面**（GCM 的规定）
  counter[3] = (counter[3] + 1) >>> 0
}

function ctrCrypt(rk, counter, input) {
  const out = new Uint8Array(input.length)
  const keystream = new Uint8Array(16)
  const ctr = Uint32Array.from(counter)
  for (let off = 0; off < input.length; off += 16) {
    // 计数器块 → 大端字节
    for (let i = 0; i < 4; i++) {
      keystream[4 * i] = (ctr[i] >>> 24) & 0xff
      keystream[4 * i + 1] = (ctr[i] >>> 16) & 0xff
      keystream[4 * i + 2] = (ctr[i] >>> 8) & 0xff
      keystream[4 * i + 3] = ctr[i] & 0xff
    }
    const block = new Uint8Array(16)
    encryptBlock(rk, keystream, 0, block, 0)
    const take = Math.min(16, input.length - off)
    for (let i = 0; i < take; i++) {
      out[off + i] = input[off + i] ^ block[i]
    }
    inc32(ctr)
  }
  return out
}

const TAG_BYTES = 16

function computeTag(rk, h, j0, aad, ciphertext) {
  const s = ghash(h, aad, ciphertext)
  const j0Bytes = new Uint8Array(16)
  for (let i = 0; i < 4; i++) {
    j0Bytes[4 * i] = (j0[i] >>> 24) & 0xff
    j0Bytes[4 * i + 1] = (j0[i] >>> 16) & 0xff
    j0Bytes[4 * i + 2] = (j0[i] >>> 8) & 0xff
    j0Bytes[4 * i + 3] = j0[i] & 0xff
  }
  const mask = new Uint8Array(16)
  encryptBlock(rk, j0Bytes, 0, mask, 0)
  const tag = new Uint8Array(16)
  for (let i = 0; i < 4; i++) {
    const m = ((mask[4 * i] << 24) | (mask[4 * i + 1] << 16) | (mask[4 * i + 2] << 8) | mask[4 * i + 3]) >>> 0
    const v = (s[i] ^ m) >>> 0
    tag[4 * i] = (v >>> 24) & 0xff
    tag[4 * i + 1] = (v >>> 16) & 0xff
    tag[4 * i + 2] = (v >>> 8) & 0xff
    tag[4 * i + 3] = v & 0xff
  }
  return tag
}

function initGcm(key) {
  const rk = expandKey(key)
  const zero = new Uint8Array(16)
  const hBytes = new Uint8Array(16)
  encryptBlock(rk, zero, 0, hBytes, 0)
  const h = new Uint32Array(4)
  for (let i = 0; i < 4; i++) {
    h[i] = ((hBytes[4 * i] << 24) | (hBytes[4 * i + 1] << 16) | (hBytes[4 * i + 2] << 8) | hBytes[4 * i + 3]) >>> 0
  }
  return { rk, h }
}

function j0FromIv(iv) {
  // 96 位 IV 的标准路径：J0 = IV || 0^31 || 1
  // 服务端用的正是 96 位（`sm4_crypto.py:88` GCM_IV_BYTES = 12）
  if (iv.length !== 12) {
    throw new Error(`本实现只支持 96 位 IV（收到 ${iv.length * 8} 位）——服务端固定用 12 字节`)
  }
  const j0 = new Uint32Array(4)
  for (let i = 0; i < 3; i++) {
    j0[i] = ((iv[4 * i] << 24) | (iv[4 * i + 1] << 16) | (iv[4 * i + 2] << 8) | iv[4 * i + 3]) >>> 0
  }
  j0[3] = 1
  return j0
}

/**
 * SM4-GCM 加密。返回 `(ciphertext, nonceTag)` —— 与 pycryptodome 的用法对齐。
 *
 * 服务端约定：`nonceTag = iv(12) || tag(16)`（`sm4_crypto.py:150-152`）。
 */
export function sm4GcmEncrypt(key, plaintext, iv, aad) {
  const { rk, h } = initGcm(key)
  const j0 = j0FromIv(iv)
  const counter = Uint32Array.from(j0)
  inc32(counter)
  const ciphertext = ctrCrypt(rk, counter, plaintext)
  const tag = computeTag(rk, h, j0, aad || new Uint8Array(0), ciphertext)
  return { ciphertext, tag }
}

/**
 * SM4-GCM 解密。
 *
 * ⚠️ **必须先验 tag 再返回明文**。GCM 的认证标签不是装饰：
 *    不验就返回，等于把一个可被随意篡改的密文当成了可信数据 ——
 *    而且篡改后解出来的"明文"长度完全正常，调用方看不出任何异常。
 */
export function sm4GcmDecrypt(key, ciphertext, iv, tag, aad) {
  const { rk, h } = initGcm(key)
  const j0 = j0FromIv(iv)
  const expected = computeTag(rk, h, j0, aad || new Uint8Array(0), ciphertext)
  let diff = 0
  for (let i = 0; i < TAG_BYTES; i++) {
    diff |= expected[i] ^ tag[i]
  }
  if (diff !== 0) {
    throw new Error('SM4-GCM 认证失败：密文或附加数据被改动，或密钥不对')
  }
  const counter = Uint32Array.from(j0)
  inc32(counter)
  return ctrCrypt(rk, counter, ciphertext)
}

/** 仅供测试：单分组加密（用于国标向量验证） */
export function sm4EncryptBlock(key, block) {
  const rk = expandKey(key)
  const out = new Uint8Array(16)
  encryptBlock(rk, block, 0, out, 0)
  return out
}

/** 仅供测试：单分组解密 */
export function sm4DecryptBlock(key, block) {
  const rk = expandKey(key)
  const out = new Uint8Array(16)
  decryptBlock(rk, block, 0, out, 0)
  return out
}
