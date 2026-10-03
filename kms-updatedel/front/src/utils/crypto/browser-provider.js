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
import { inspectNodeKeys, listSecrets, removeSecret, requireLocalKey, sealSecret, unsealSecret, hasSecret } from './node-key-store.js'
// KMS-003：keyRef 的格式由 key-ref.js 独占定义 —— 本模块只**使用**它，绝不自己拼。
// 之所以要收口：手拼的 ref 即使拼错也不会当场报错，只会让私钥在"本机有没有该节点的
// 材料"的检查里悄悄消失（`inspectNodeKeys` 按规范分段匹配），而私钥其实还躺在库里。
import {
  buildKeyRef,
  mintKeyId,
  parseKeyRef,
  KeyRefError,
  ERR_INVALID_PARAMETER,
  ERR_KEY_VERSION_MISMATCH
} from './key-ref.js'

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
 * 把"字节的任意一种常见形态"归一成 `Uint8Array`，不是字节就返回 null。
 *
 * 为什么需要它：密码学库回的东西形态不统一 —— 实测 Kyber 的 `Encrypt768`
 * 返回的是**普通数字数组**（1088 个元素），Falcon 那边是 Uint8Array，
 * 服务端来的又是 hex/base64 文本。而 `decapsulate` 原先只认
 * `Uint8Array` 与 hex 串两种，于是 `decapsulate(encapsulate(...))`
 * 这条**自检赖以成立的往返**把数字数组送进了 `fromHex`，
 * 报"不是合法的十六进制串" —— 这句话读起来像"密钥不对"，
 * 排查方向会被带偏到密钥材料本身（实测自检里就是这个现象）。
 */
export const toBytes = (value) => {
  if (value instanceof Uint8Array) return value
  if (value instanceof ArrayBuffer) return new Uint8Array(value)
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength)
  if (Array.isArray(value)) return Uint8Array.from(value)
  return null
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

/**
 * hex/字节 → base64。`b64ToHex` 的反方向，给**封装**方向用（KMS-009）。
 *
 * ⚠️ 必须分块喂 `String.fromCharCode`：它一次收一个参数表，
 *    把上万个字节摊成实参会爆栈（"Maximum call stack size exceeded"），
 *    而那句报错完全看不出是编码问题。分块大小取 4096，与字节数无关地安全。
 */
export function bytesToB64(value) {
  const bytes = toBytes(value) || fromHex(value)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 4096) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 4096))
  }
  return btoa(binary)
}

//: Kyber 变体。**变体由公钥长度自描述**（服务端 `wrappers.py` 的 pk_len_map 同口径），
//: 所以两边不必预先约定 —— 但生成时要选一个，默认 768（NIST 3 级）。
const KYBER_VARIANTS = {
  512: { k: 'KeyGen512', enc: 'Encrypt512', dec: 'Decrypt512' },
  768: { k: 'KeyGen768', enc: 'Encrypt768', dec: 'Decrypt768' },
  1024: { k: 'KeyGen1024', enc: 'Encrypt1024', dec: 'Decrypt1024' }
}

//: 公钥字节数 → 变体。`decapsulate` 按**私钥**长度推断（1632/2400/3168），
//: 这里按**公钥**长度（800/1184/1568）—— 两张表是同一件事的两面，不要合并成一张
//: "按长度推断"的表：两者的长度集合不相交，合并后一旦有人传错一侧（拿公钥去解封装），
//: 会得到一个"看起来算过了"的错误结果。
//:
//: 导出给**展示**用（密钥历史页按字节数标出 Kyber 变体）：变体对不上是
//: "封装出来的密文对方解不开"的直接线索，而它在界面上只表现为一个字节数。
export const KYBER_PK_LENGTHS = { 800: 512, 1184: 768, 1568: 1024 }

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
   * ⚠️ keyRef **不由本方法拼**，而是交给 `key-ref.js` 生成规范格式
   *    （`node/{nodeId}/{algorithm}/{keyId}/{version}`）。页面与 provider 都不许手拼：
   *    拼错不会当场报错，只会让私钥在"本机有没有该节点的材料"的检查里消失 ——
   *    `inspectNodeKeys` 是按规范分段匹配的，届时已很难追到原因。
   *
   * @param {string} algorithm
   * @param {object} options
   * @param {string} options.nodeId   必填（KMS-003：本地密钥必须挂在具体节点下）
   * @param {string} [options.keyId]  指定 keyId（不给则按节点+算法铸一个新的）
   * @param {number} [options.version] 版本号（默认 1）
   * @param {number} [options.variant] Kyber 变体（512/768/1024，默认 768）
   */
  async generate(algorithm, options = {}) {
    const name = normalizeAlgorithm(algorithm)
    const nodeId = String(options.nodeId || '').trim()
    if (!nodeId) {
      throw new KeyRefError('本地密钥必须挂在具体节点下（缺少 nodeId）', ERR_INVALID_PARAMETER)
    }
    // 旧实现在这里用 `${算法}-${randomUUID}` 兜底出一个 ref —— 那正是
    // "ref 不由格式模块产生"的漏洞：它看上去能用，却过不了规范格式的检查。
    // 已删除，不再保留任何手拼路径。
    const keyId = options.keyId ? String(options.keyId) : mintKeyId(nodeId, name)
    const version = Number(options.version || 1)
    const keyRef = buildKeyRef({ nodeId, algorithm: name, keyId, version })

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
      return { publicKey, keyRef, keyId, nodeId, version, algorithm: name, variant }
    }

    if (name === 'FALCON') {
      const falcon = await loadFalcon()
      const kp = falcon.falcon512.keygen()
      const publicKey = toHex(kp.publicKey)
      await sealSecret(keyRef, { algorithm: name, secret: toHex(kp.secretKey), publicKey, version })
      return { publicKey, keyRef, keyId, nodeId, version, algorithm: name, variant: 512 }
    }

    if (name === 'SM2' || name === 'SSCL') {
      // 无证书路径：节点侧只产生秘密份额 u，公开量 uA = u·G。
      // `u` 从不外传；KGC 的返回（部分密钥）由上层合成成 d_A 后再落到这里。
      const { SM2 } = await import('gm-crypto')
      const { publicKey, privateKey } = SM2.generateKeyPair()
      await sealSecret(keyRef, { algorithm: name, secret: String(privateKey).toLowerCase(), publicKey, version })
      return { publicKey, keyRef, keyId, nodeId, version, algorithm: name }
    }

    throw new Error(`不支持的算法：${algorithm}`)
  }

  /**
   * 把已有材料纳入本地密钥库（用于无证书合成后的 d_A、或从密钥文件导入）。
   *
   * KMS-003 起 ref 必须是规范格式（`node/{nodeId}/{algorithm}/{keyId}/{version}`），
   * 且算法与版本以 **ref 为准**：调用方显式传了与 ref 冲突的值就直接抛错 ——
   * 静默采纳任意一方，都会把"记录按 ref 找得到、按算法/版本却对不上"的不一致
   * 留到运行期才现形。设备凭据（`node-{id}-device-auth`）不是长期密钥，不能从这里导入。
   */
  async importSecret(keyRef, { algorithm, secret, publicKey = '', version }) {
    const parsed = parseKeyRef(keyRef)
    if (!parsed || parsed.kind !== 'node') {
      throw new KeyRefError(
        `只能导入挂在节点下的长期密钥（node/{nodeId}/{algorithm}/{keyId}/{version}），收到：${keyRef}。` +
          '设备凭据不是长期密钥，不能走这里',
        ERR_INVALID_PARAMETER
      )
    }
    if (algorithm) {
      const name = normalizeAlgorithm(algorithm)
      if (name !== parsed.algorithm) {
        throw new KeyRefError(
          `导入的算法与 keyRef 不一致：keyRef 是 ${parsed.algorithm}，调用方传的是 ${name}`,
          ERR_INVALID_PARAMETER
        )
      }
    }
    // 未传 version 时用 ref 里的版本（不设 `= 1` 默认值，否则"没传"与"传 1"分不开，
    // ref 版本不是 1 时会被误判成冲突）
    if (version !== undefined && version !== null && Number(version) !== parsed.version) {
      throw new KeyRefError(
        `导入的版本与 keyRef 不一致：keyRef 是 ${parsed.version}，调用方传的是 ${version}`,
        ERR_KEY_VERSION_MISMATCH
      )
    }
    // 算法与版本一律取 ref 的派生值，不取调用方传的 —— 两边说法不一时以 ref 为准
    const sealed = await sealSecret(keyRef, { algorithm: parsed.algorithm, secret, publicKey, version: parsed.version })
    // 返回**落库后的** ref（sealSecret 会把别名文本重建为规范文本）：调用方拿
    // 返回值去 hasKey/sign/decapsulate 才找得到。返回入参那份，遇到 `kyber_kem`
    // 这类可解析但非规范的写法就会静默查不到 —— 而那正是本任务要根除的模式。
    return {
      keyRef: sealed.keyRef,
      nodeId: parsed.nodeId,
      keyId: parsed.keyId,
      version: parsed.version,
      algorithm: parsed.algorithm
    }
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
    // 密文可能是字节（`encapsulate` 的返回值）或 hex 文本（信封里的形式）——
    // 前者要能直接回传进来，`decapsulate(encapsulate(...))` 才是成立的往返。
    const ct = toBytes(ciphertext) || fromHex(ciphertext)
    // 变体按**私钥长度**推断：服务端 `wrappers.py:325` 是同一口径
    // （sk 长度 → 512/768/1024），两边不必预先约定。
    const variant = { 1632: 512, 2400: 768, 3168: 1024 }[skBytes.length]
    if (!variant) {
      throw new Error(`无法从私钥长度推断 Kyber 变体：${skBytes.length} 字节`)
    }
    const names = kyberNames(variant)
    return kyber[names.dec](ct, skBytes)
  }

  /**
   * Kyber 封装：公钥 → `(密文, 共享密钥)`。发送节点在**收件方公钥**上做这一步。
   *
   * 与 `decapsulate` 是一对：`decapsulate(encapsulate().ciphertext)` 必须还原出
   * **逐字节相同**的共享密钥。这是本仓库对 Kyber 的唯一判据 —— round-3 与
   * ML-KEM 的错误组合**不会报错**，只会安静地返回另一串长度完全正确的字节。
   *
   * 变体由**公钥长度**推断（与 `decapsulate` 按私钥长度推断同一口径，
   * 服务端 `wrappers.py` 亦同）。
   *
   * @param {string} algorithm 只有 KYBER 有真正的封装原语，见下
   * @param {string|Uint8Array} publicKey 十六进制或原始字节
   * @returns {Promise<{ciphertext: Uint8Array, sharedSecret: Uint8Array, algorithm: string, variant: number}>}
   */
  async encapsulate(algorithm, publicKey) {
    const name = normalizeAlgorithm(algorithm)
    // Falcon 是**签名**算法，没有封装原语。历史实现把它当保护算法用
    // （`falcon_lattice` = "用 Falcon 公钥封装 SM4"），那是本计划 §3 点名否定的
    // 概念错误 —— 签名密钥无法生成共享秘密，硬凑出来的"封装"既不安全也无从验证。
    // 这里明确拒绝并说明该用什么，而不是"能算出个数就返回"。
    if (name === 'FALCON') {
      throw new Error(
        'Falcon 是签名算法，没有封装原语：要用密钥封装请改选 KYBER，' +
          'FALCON 只用于签名与验签（历史 falcon_lattice 的做法已被否定）'
      )
    }
    if (name !== 'KYBER') {
      throw new Error(
        `encapsulate 暂只支持 KYBER，收到：${algorithm}。` +
          'SM2 / SSCL 的节点腿走**信封加密**（对载荷本身加密），不是 KEM —— 那一步归 KMS-009。'
      )
    }
    const kyber = await loadKyber()
    const pk = toBytes(publicKey) || fromHex(publicKey)
    const variant = KYBER_PK_LENGTHS[pk.length]
    if (!variant) {
      throw new Error(
        `无法从公钥长度推断 Kyber 变体：${pk.length} 字节（期望 800 / 1184 / 1568）`
      )
    }
    const names = kyberNames(variant)
    // Encrypt 返回 [ciphertext, sharedSecret]，与 KeyGen 一样**不收变体参数**。
    // ⚠️ 且**不保证是 Uint8Array**（Kyber 这边实测是普通数字数组）——返回前
    //    统一字节化，否则调用方按声明类型用（`decapsulate` 再解回来）会踩空。
    const [ct, shared] = kyber[names.enc](pk)
    const ciphertext = toBytes(ct)
    const sharedSecret = toBytes(shared)
    if (!ciphertext || !sharedSecret) {
      throw new Error('Kyber 封装返回了认不出的字节形态（期望 Uint8Array / ArrayBuffer / 数字数组）')
    }
    return { ciphertext, sharedSecret, algorithm: name, variant }
  }

  /**
   * 用**接收方的公钥**把载荷密钥封成一份**节点腿信封**（KMS-009）。
   *
   * 与 `encapsulate` 的分工：那个是 KEM **原语**（返回密文与共享秘密，剩下的事
   * 调用方自己干）；本方法产出的是**可以直接落库、对面可以直接解**的成品信封，
   * 形状与服务端 `wrappers.wrap_with_public_key` 逐字段对应。
   *
   * 为什么放在 provider 里而不是页面里：这是密码学动作（KEM/KEX + DEM 的组合），
   * 与 `unwrapEnvelope` 是严格的一对 —— 对面就是拿 `unwrapEnvelope` 解它的。
   * 分散到页面里，等于让"封"与"解"两侧各自的实现漂移，而漂移的表现是
   * **能封、开不开**（GCM 认证失败或 SM2 完整性校验失败），报错看起来像密钥不对。
   *
   * @param {string} algorithm 保护算法：KYBER / SM2 / SSCL（规范名或历史拼写都认）
   * @param {string} recipientPublicKeyHex 接收方公钥（hex；KYBER 由内部转成字节）
   * @param {Uint8Array} payloadKey 16 字节 SM4 载荷密钥
   * @returns {Promise<{envelope: object, wrapping: string}>} `wrapping` 是库内口径的算法拼写
   */
  async wrapForPeer(algorithm, recipientPublicKeyHex, payloadKey) {
    const name = normalizeAlgorithm(algorithm)
    const publicKeyHex = String(recipientPublicKeyHex || '').trim().toLowerCase()
    const key = toBytes(payloadKey)
    if (!key || key.length !== 16) {
      throw new Error(`载荷密钥必须是 16 字节的 SM4 密钥（收到 ${key ? `${key.length} 字节` : '非字节'}）`)
    }

    if (name === 'KYBER') {
      const { sm4GcmEncrypt } = await import('../sm4.js')
      const encapsulated = await this.encapsulate('KYBER', publicKeyHex)
      // KEK 取共享秘密**前 16 字节** —— 与服务端
      // `PayloadCipher.kek_from_shared_secret('sm4', ss)` 同一口径。
      // 取错长度不会报错，只会解出乱码。
      const kek = encapsulated.sharedSecret.slice(0, 16)
      const iv = crypto.getRandomValues(new Uint8Array(12))
      // ⚠️ **不传 aad**：服务端封装时也没传（`wrappers.py` 的 kyber 分支），
      //    这里传了就会"能封、开不开"，而报错是 GCM 认证失败。
      const { ciphertext, tag } = sm4GcmEncrypt(kek, key, iv)
      return {
        wrapping: 'kyber_kem',
        envelope: {
          kem_ciphertext: bytesToB64(encapsulated.ciphertext),
          encrypted_key: bytesToB64(ciphertext),
          nonce: bytesToB64(iv),
          tag: bytesToB64(tag),
          payload_algorithm: 'sm4',
          wrapping_algorithm: 'kyber_kem'
        }
      }
    }

    if (name === 'SM2' || name === 'SSCL') {
      const { SM2 } = await import('gm-crypto')
      // ⚠️ gm-crypto 的 `encrypt` 返回 **ArrayBuffer**，且 C1 **不带 `04`
      //    未压缩点前缀**（实测比国标格式少 2 个字符）。直接当密文用会被
      //    `decryptEnvelope` 判"C1 不是未压缩点" —— 而那句报错听起来像
      //    "密钥不对"。补回前缀（下面 selfTest 里那处是同一个坑）。
      //
      // ⚠️ 入参必须是 **ArrayBuffer**，不是 Uint8Array —— gm-crypto 里判的是
      //    `instanceof ArrayBuffer`，而 Uint8Array **是视图不是 ArrayBuffer**，
      //    会被它拒成 `Expected "string" | "Buffer" | "ArrayBuffer" but received
      //    "[object Uint8Array]"`。`Uint8Array.from` 复制一份再取 `.buffer`，
      //    顺带避开"传进去的是别人 buffer 的一段视图"这种更难查的情形。
      const raw = SM2.encrypt(Uint8Array.from(key).buffer, publicKeyHex)
      const wrapping = name === 'SM2' ? 'gm_sm2' : 'gm_sscl'
      const envelope = {
        algorithm: 'sm2',
        ciphertext: '04' + toHex(new Uint8Array(raw)),
        public_key: publicKeyHex,
        payload_algorithm: 'sm4',
        wrapping_algorithm: wrapping,
        recipient_public_key: publicKeyHex
      }
      if (name === 'SSCL') {
        // `key_system` 表达"密钥体系"，与 `algorithm`（密码算法，必须恒为 'sm2'，
        // 解密侧会校验）是两件事 —— 服务端 `SsclWrapper.wrap` 同此口径。
        envelope.key_system = 'sscl'
      }
      return { wrapping, envelope }
    }

    throw new Error(
      `wrapForPeer 不支持 ${algorithm}：保护算法只允许 KYBER / SM2 / SSCL` +
        '（Falcon 是签名算法，不提供机密性）'
    )
  }

  /**
   * 自检：用**本地这份材料**真跑一轮加解密/签名验证。
   *
   * 为什么不能只检查形状
   * --------------------
   * 密钥库里躺着的材料可能是上一代格式、别的算法、或与登记的公钥**不成对**
   * 的一份（换设备、手工导入、迁移残留都会造成）。这三种情况长度对得上、
   * 字段齐全、"看起来是好的"，只有真正用一次才现形。而现形的时机若是
   * 第一次真实分发，代价是别人的会话 —— 所以生成页当场验一次。
   *
   * 各算法的验法
   * ------------
   * - **KYBER**：`encapsulate`（用登记的公钥）→ `decapsulate`（用本地私钥），
   *   两边共享秘密必须**逐字节**相等。这一条同时覆盖"公钥与私钥成对"与
   *   "实现版本正确"。
   * - **FALCON**：签名 → 用登记公钥验签，并比对还原出的消息。
   * - **SM2 / SSCL**：用 gm-crypto 加密、再用**本仓库自己的** `sm2-envelope.js`
   *   解开。刻意不两边都用 gm-crypto —— 那样只证明"gm-crypto 自洽"，而线上
   *   解信封走的是仓库那一份实现，两者一旦不一致，自检会绿、线上却解不开。
   *
   * 失败**不抛错**：它是结论的一种（"这把不能用"），不是调用错误。
   * 抛错会让调用方把"材料坏了"与"参数写错了"混在一起处理。
   *
   * @param {string} algorithm
   * @param {string} keyRef
   * @returns {Promise<{ok: boolean, detail: string}>}
   */
  async selfTest(algorithm, keyRef) {
    const name = normalizeAlgorithm(algorithm)
    try {
      // `requireLocalKey` 顺带把 ref 形状、节点归属、算法、版本全查一遍 ——
      // 自检的输入本身也要是规范的，否则"测过了"测的是别的东西。
      const summary = await requireLocalKey(keyRef, { algorithm: name })
      const publicKey = String(summary.publicKey || '')

      if (name === 'KYBER') {
        if (!publicKey) {
          return { ok: false, detail: '本地记录里没有公钥，无法验证私钥是否正确（重新生成一次）' }
        }
        const { ciphertext, sharedSecret, variant } = await this.encapsulate('KYBER', publicKey)
        const recovered = await this.decapsulate('KYBER', keyRef, ciphertext)
        if (toHex(recovered) !== toHex(sharedSecret)) {
          return {
            ok: false,
            detail: '封装与解封装得到的共享秘密不一致：本地私钥与登记的公钥不是一对（解封会失败）'
          }
        }
        return {
          ok: true,
          detail: `Kyber-${variant} 封装/解封装往返一致（共享秘密 ${sharedSecret.length} 字节逐字节相同）`
        }
      }

      if (name === 'FALCON') {
        if (!publicKey) {
          return { ok: false, detail: '本地记录里没有公钥，无法验签（重新生成一次）' }
        }
        const message = textEncoder.encode(`kms-selftest-${Date.now()}`)
        const signature = await this.sign('FALCON', keyRef, message)
        const passed = await this.verify('FALCON', publicKey, signature, message)
        return passed
          ? { ok: true, detail: 'Falcon 签名 / 验签往返一致（含还原消息比对）' }
          : { ok: false, detail: '签名能产生但验签不过：本地私钥与登记的公钥不是一对' }
      }

      if (name === 'SM2' || name === 'SSCL') {
        if (!publicKey) {
          return { ok: false, detail: '本地记录里没有公钥，无法加密验证（重新生成一次）' }
        }
        const { SM2 } = await import('gm-crypto')
        const { decryptEnvelope } = await import('../sm2-envelope.js')
        const probe = `kms-selftest-${Date.now()}`
        // ⚠️ gm-crypto 的 `encrypt` 返回的是 **ArrayBuffer**，且其中的 C1
        //     **不带 `04` 未压缩点前缀**（实测：hex 长度比国标格式少 2 个字符）。
        //     直接当密文用会被 `decryptEnvelope` 判"C1 不是未压缩点"——
        //     而后者的报错听起来像"密钥不对"，很容易查错方向。这里补回前缀。
        const raw = SM2.encrypt(probe, publicKey)
        const ciphertext = '04' + toHex(new Uint8Array(raw))
        const plain = decryptEnvelope({ algorithm: 'sm2', ciphertext }, await this._secretHex(keyRef))
        const text = new TextDecoder().decode(plain)
        if (text !== probe) {
          return { ok: false, detail: `解出的明文与原文不符（得到 ${text.length} 字节）` }
        }
        return {
          ok: true,
          detail: `${name} 加密 / 生产解密路径往返一致（经 sm2-envelope.js 解开）`
        }
      }

      return { ok: false, detail: `自检不认识算法：${algorithm}` }
    } catch (error) {
      return { ok: false, detail: `自检失败：${error?.message || error}` }
    }
  }

  /** 读回私密材料的 **hex 文本**（SM2/SSCL 的解密路径要的是 hex 标量，不是字节） */
  async _secretHex(keyRef) {
    return new TextDecoder().decode(await unsealSecret(keyRef))
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

  /**
   * 本机对某节点的密钥持有哪些（§4.4 设备绑定）。
   *
   * 上层用它判断"我是不是那台设备"，进而决定是续做、重新初始化还是轮换。
   * 判据是"任意一套在不在本机"而非"四套都在"：
   * 初始化做到一半同样是"本机有材料"，与"新设备什么都没有"必须区分开。
   */
  async inspectNodeKeys(nodeId) {
    return inspectNodeKeys(nodeId)
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