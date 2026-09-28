/**
 * `BrowserCryptoProvider` —— 节点侧密码能力的浏览器实现（文档 §4.4）。
 *
 * 定位：**浏览器只是「节点侧」当前选用的运行环境**，不是"客户端密码学"这个
 * 概念本身。这一区分很重要 —— 之所以把它写成 CryptoProvider 的一个实现，
 * 就是为了让将来换成节点本地 Agent / TPM / HSM 时，上层业务一行不改。
 *
 * 私密材料一律经 `node-key-store` 加密落 IndexedDB，**不上传、不落 localStorage**。
 *
 * 各算法用的是什么实现
 * --------------------
 * | 算法 | 实现 | 备注 |
 * |---|---|---|
 * | SM2 / SSCL | `gm-crypto` + `utils/cl-key.js` | 无证书份额协议，KGC 参与 |
 * | Kyber | `crystals-kyber` | **round-3**，已实测与服务端 `.so` 共享密钥逐字节相同 |
 * | Falcon | `@noble/post-quantum/falcon.js` | **round-3**，已实测双向验签互通 |
 *
 * ⚠️ Kyber 与 Falcon 的实现都**必须**是 round-3 版本，不能换成 ML-KEM / FN-DSA。
 *    这一条踩过两次坑，且**两次都不报错**：
 *      * Kyber：解错了只会返回另一个共享密钥，长度格式全对；
 *      * Falcon：编码格式不一致会表现成"验签失败"，看不出是版本问题。
 *    唯一的判据是**逐字节比对**（见 `_research/` 下的互通用例）。
 *    另：`falcon512padded` 与 `falcon512` 是**两套不同的线上格式**，
 *    服务端的参考实现对应的是 `falcon512`，不要混用。
 */

// 显式写 `.js` 后缀：Vite 两种都接受，而 Node 的 ESM **必须**有后缀 ——
// 这样本模块才能被验证脚本直接 import 进 Node 跑（见 `_probe-provider.mjs`），
// 否则只能在浏览器里靠肉眼观察，而密码学路径最不能靠肉眼。
import { CryptoProvider, normalizeAlgorithm } from './provider.js'
import { listSecrets, removeSecret, sealSecret, unsealSecret, hasSecret } from './node-key-store.js'

// ---------------------------------------------------------------------------
// 惰性加载重依赖
// ---------------------------------------------------------------------------
// 这两个包只在真正生成/使用该类密钥时才需要。静态 import 会让它们进入主包，
// 而绝大多数页面根本不碰 PQ —— 按需动态 import 既省首屏体积，
// 也让"没用 PQ 的部署"不必为它们付出代价。
let kyberModule = null
let falconModule = null

async function loadKyber() {
  if (!kyberModule) {
    kyberModule = await import('crystals-kyber')
  }
  return kyberModule
}

async function loadFalcon() {
  if (!falconModule) {
    falconModule = await import('@noble/post-quantum/falcon.js')
  }
  return falconModule
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------
const textEncoder = new TextEncoder()

export const toHex = (bytes) => [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
export const fromHex = (hex) => {
  const text = String(hex || '').trim().toLowerCase()
  if (!/^[0-9a-f]*$/.test(text) || text.length % 2) {
    throw new Error('不是合法的十六进制串')
  }
  return Uint8Array.from(text.match(/.{2}/g)?.map((b) => parseInt(b, 16)) || [])
}

/**
 * base64 → hex。
 *
 * 信封里的二进制字段是 base64（服务端 `wrappers.py` 用 `base64.b64encode`），
 * 而本 provider 内部一律按 hex 走 —— 转换只在这一处发生，
 * 免得各调用点各转一套，错了要等到"解出来是乱码"才发现。
 */
function b64ToHex(value) {
  const binary = atob(String(value || ''))
  let out = ''
  for (let i = 0; i < binary.length; i++) {
    out += binary.charCodeAt(i).toString(16).padStart(2, '0')
  }
  return out
}

//: Kyber 变体。**变体由公钥长度自描述**（服务端 `wrappers.py` 的 pk_len_map 同口径），
//: 所以两边不必预先约定 —— 但生成时要选一个，默认 768（NIST 3 级）。
const KYBER_VARIANTS = { 512: { k: 'KeyGen512', dec: 'Decrypt512' }, 768: { k: 'KeyGen768', dec: 'Decrypt768' }, 1024: { k: 'KeyGen1024', dec: 'Decrypt1024' } }

function kyberNames(variant) {
  const entry = KYBER_VARIANTS[variant]
  if (!entry) {
    throw new Error(`不支持的 Kyber 变体：${variant}（可选 512 / 768 / 1024）`)
  }
  return entry
}

// ---------------------------------------------------------------------------
// 实现
// ---------------------------------------------------------------------------
export class BrowserCryptoProvider extends CryptoProvider {
  /**
   * 生成一份新的密钥材料。私密部分落本地密钥库，返回公开量与引用。
   *
   * @param {string} algorithm
   * @param {object} [options]
   * @param {string} [options.keyRef]  指定引用（不给则自动生成）
   * @param {number} [options.variant] Kyber 变体（512/768/1024，默认 768）
   * @param {number} [options.version]
   */
  async generate(algorithm, options = {}) {
    const name = normalizeAlgorithm(algorithm)
    const keyRef = options.keyRef || `${name.toLowerCase()}-${crypto.randomUUID?.() || Date.now()}`
    const version = options.version || 1

    if (name === 'KYBER') {
      const variant = options.variant || 768
      const names = kyberNames(variant)
      const kyber = await loadKyber()
      // KeyGen 返回 [publicKey, secretKey]。**不收参数** —— 变体由函数名区分
      // （KeyGen512/768/1024），别顺手把 variant 当参数传进去：JS 会默默忽略多余实参，
      // 于是 512 的请求拿到 768 的密钥而没有任何报错。
      const [pk, sk] = kyber[names.k]()
      const publicKey = toHex(pk)
      await sealSecret(keyRef, { algorithm: name, secret: toHex(sk), publicKey, version })
      return { publicKey, keyRef, algorithm: name, variant }
    }

    if (name === 'FALCON') {
      const falcon = await loadFalcon()
      const kp = falcon.falcon512.keygen()
      const publicKey = toHex(kp.publicKey)
      await sealSecret(keyRef, { algorithm: name, secret: toHex(kp.secretKey), publicKey, version })
      return { publicKey, keyRef, algorithm: name, variant: 512 }
    }

    if (name === 'SM2' || name === 'SSCL') {
      // 无证书路径：节点侧只产生秘密份额 u，公开量 uA = u·G。
      // `u` 从不外传；KGC 的返回（部分密钥）由上层合成成 d_A 后再落到这里。
      const { SM2 } = await import('gm-crypto')
      const { publicKey, privateKey } = SM2.generateKeyPair()
      await sealSecret(keyRef, { algorithm: name, secret: String(privateKey).toLowerCase(), publicKey, version })
      return { publicKey, keyRef, algorithm: name }
    }

    throw new Error(`不支持的算法：${algorithm}`)
  }

  /** 把已有材料纳入本地密钥库（用于无证书合成后的 d_A、或从密钥文件导入） */
  async importSecret(keyRef, { algorithm, secret, publicKey = '', version = 1 }) {
    await sealSecret(keyRef, { algorithm: normalizeAlgorithm(algorithm), secret, publicKey, version })
    return { keyRef, algorithm: normalizeAlgorithm(algorithm) }
  }

  /** 用 keyRef 的私钥签名。返回**附加格式**（与服务端 NIST 包装一致），可直接上链/入库。 */
  async sign(algorithm, keyRef, message) {
    const name = normalizeAlgorithm(algorithm)
    if (name !== 'FALCON') {
      throw new Error(`sign 暂只支持 FALCON，收到：${algorithm}`)
    }
    const falcon = await loadFalcon()
    const sk = await this._secretBytes(keyRef)
    const bytes = typeof message === 'string' ? textEncoder.encode(message) : message
    // ⚠️ 必须用 attached.seal，**不能**自己拼 sig‖msg。
    //    服务端参考实现的布局是（falcon512int/nist.c:178-191）：
    //        [签名长度 2B 大端] ‖ nonce(40B) ‖ 消息 ‖ 签名
    //    签名在消息**之后**、中间还夹着 40 字节 nonce —— 自己拼必然拼错，
    //    而现象只是服务端 crypto_sign_open 返回 -1（"验签失败"），
    //    完全看不出是格式问题。这个坑实测踩过。
    return falcon.falcon512.attached.seal(bytes, sk)
  }

  /** 用公钥验签。`signature` 为附加格式。 */
  async verify(algorithm, publicKey, signature, message) {
    const name = normalizeAlgorithm(algorithm)
    if (name !== 'FALCON') {
      throw new Error(`verify 暂只支持 FALCON，收到：${algorithm}`)
    }
    const falcon = await loadFalcon()
    const bytes = typeof message === 'string' ? textEncoder.encode(message) : message
    try {
      const opened = falcon.falcon512.attached.open(
        signature instanceof Uint8Array ? signature : fromHex(signature),
        fromHex(publicKey)
      )
      // 附加格式会把消息一并还原出来 —— 顺带校验它确实是我们签的那条，
      // 否则"验签通过"只说明签名结构合法，不说明签的是这条消息。
      return toHex(opened) === toHex(bytes)
    } catch {
      return false
    }
  }

  /** Kyber 解封装：密文 + 本地私钥 → 共享密钥 */
  async decapsulate(algorithm, keyRef, ciphertext) {
    const name = normalizeAlgorithm(algorithm)
    if (name !== 'KYBER') {
      throw new Error(`decapsulate 只适用于 KYBER，收到：${algorithm}`)
    }
    const kyber = await loadKyber()
    const skBytes = await this._secretBytes(keyRef)
    const ct = ciphertext instanceof Uint8Array ? ciphertext : fromHex(ciphertext)
    // 变体按**私钥长度**推断：服务端 `wrappers.py:325` 是同一口径
    // （sk 长度 → 512/768/1024），两边不必预先约定。
    const variant = { 1632: 512, 2400: 768, 3168: 1024 }[skBytes.length]
    if (!variant) {
      throw new Error(`无法从私钥长度推断 Kyber 变体：${skBytes.length} 字节`)
    }
    const names = kyberNames(variant)
    return kyber[names.dec](ct, skBytes)
  }

  async hasKey(keyRef) {
    return hasSecret(keyRef)
  }

  /**
   * 解开一个**节点腿**信封，取出其中的 SM4 载荷密钥。
   *
   * 这是 §6.5 那条「接收节点成功恢复 SM4 会话密钥」在客户端的落地 ——
   * 在此之前它**从未发生过**：服务端只封装、入库，然后就停在那里
   * （`views.py` 里那几处 decaps 都在前端不调用的旧端点里）。
   *
   * 三种节点腿的封装格式（`wrappers.wrap_for_node`）：
   *
   * | wrapping_algorithm | 信封形状 | 解封方式 |
   * |---|---|---|
   * | `kyber_kem` | `{kem_ciphertext, encrypted_key, nonce, tag}` | Kyber decaps → KEK → SM4-GCM |
   * | `gm_sm2` / `gm_sscl` | `{algorithm:'sm2', ciphertext: C1‖C3‖C2}` | 直接用节点 d_A 解 |
   *
   * ⚠️ 三条腿解出来的必须是**同一把** K。用户那份走国密、节点那份走抗量子，
   *    算法不同但 K 相同 —— 这是 D10 方案 A 成立的根本。所以这里
   *    绝不能再生成一把，只能解出信封里那把。
   *
   * @returns {Promise<Uint8Array>} SM4 载荷密钥
   */
  async unwrapEnvelope(algorithm, keyRef, envelope) {
    const wrapping = String(envelope?.wrapping_algorithm || algorithm || '').trim().toLowerCase()

    if (wrapping === 'kyber_kem') {
      const { sm4GcmDecrypt } = await import('../sm4.js')
      const shared = await this.decapsulate('KYBER', keyRef, fromHex(b64ToHex(envelope.kem_ciphertext)))
      // KEK 取共享秘密**前 16 字节** —— 与服务端
      // `PayloadCipher.kek_from_shared_secret('sm4', ss)` 同一口径
      // （`sm4_crypto.py:312`）。取错长度不会报错，只会解出乱码。
      const kek = shared.slice(0, 16)
      return sm4GcmDecrypt(
        kek,
        fromHex(b64ToHex(envelope.encrypted_key)),
        fromHex(b64ToHex(envelope.nonce)),
        fromHex(b64ToHex(envelope.tag))
      )
    }

    if (wrapping === 'gm_sm2' || wrapping === 'gm_sscl') {
      const { decryptEnvelope } = await import('../sm2-envelope.js')
      const privateKeyHex = toHex(await this._secretBytes(keyRef))
      // 节点腿的国密信封与用户腿是**同一套 SM2Crypto**（`wrappers.py:120`
      // 复用它而非另写），所以直接复用本仓库已验证的浏览器实现。
      // 信封里 `algorithm` 恒为 'sm2'（节点腿用哪种档位由 wrapping_algorithm 表达），
      // 因此 SSCL 也走同一条解密路径。
      return decryptEnvelope(envelope, privateKeyHex)
    }

    throw new Error(
      `不支持的节点腿封装算法：${wrapping || '(空)'}。` +
        '当前支持 kyber_kem / gm_sm2 / gm_sscl。'
    )
  }

  async destroy(keyRef) {
    await removeSecret(keyRef)
  }

  /** 列出本地持有的全部密钥摘要（不含私密材料）—— 设备绑定判断用它 */
  async listLocalKeys() {
    return listSecrets()
  }

  /** 读回私密材料的字节形式。**只在本模块内部使用**，不外泄给上层。 */
  async _secretBytes(keyRef) {
    const plain = await unsealSecret(keyRef)
    // 存进去时统一是 hex 文本，取出来仍按 hex 解析
    return fromHex(new TextDecoder().decode(plain))
  }
}

/** 进程内默认实例。上层用它即可；将来换 AgentProvider 只改这一行。 */
export const cryptoProvider = new BrowserCryptoProvider()