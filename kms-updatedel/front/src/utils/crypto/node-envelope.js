/**
 * KMS-011：接收方对**节点腿信封**的验签、解封与持有证明（协议层，不出 HTTP）。
 *
 * 它解决的问题
 * ------------
 * KMS-009/010 之后，节点腿信封由**发送节点**产出并签名、由服务端验签后登记。
 * 但"接收方自己也能验一次"这一步一直缺着 —— 而在本系统里它必须由接收方
 * 在本机完成：发送方公钥要**回到登记表里那一版**、解封要**接收方自己的私钥**
 * （私钥只在本地，服务端做不了也不该做）。
 *
 * 于是本模块把三段纯协议动作收在一处：
 *   1. `verifyNodeEnvelope` —— 用发送方那一版 Falcon 公钥验信封签名。
 *      重建被签字节串**必须用服务端同一份规范**（`nodeCanonicalPayload`，
 *      `envelope-signing.js` 里那份）—— 另写一份必然漂移，而漂移的表现是
 *      "所有信封都验不过"，看起来像伪造。
 *   2. `unwrapNodeEnvelope` —— 用本机那把私钥解出 SM4 载荷密钥（K）。
 *   3. `nodeProof` —— 立刻算出 `HMAC-SHA256(K, session_id)`，交给服务端与
 *      对方比对。服务端**始终看不到 K**（那是不变量），所以它只能比 proof。
 *
 * ⚠️ 解出 K 之后要**立刻自查 `key_hash`**（`checkRecoveredKeyHash`）：
 *    信封里带着 `sha256(K)` 的声明。验它能把"解出来了但解错了一把"
 *    变成一个当场可见的失败，而不是等到双方 proof 对不上才发现 ——
 *    那时错误现场已经隔了两个节点、一次 HTTP 往返与一层确认。
 *
 * ⚠️ 这些函数**不碰接口、不写状态**。状态推进（recipient_verified /
 *    key_recovered）由调用方在拿到结论之后调 `/node-self/envelopes/<id>/verify|recover/`
 *    如实回报 —— 服务端据此按 `SESSION_TRANSITIONS` 推进。
 */
import {
  b64ToHex,
  cryptoProvider,
  fromHex,
  toBytes,
  toHex
} from './browser-provider.js'
import { keyHashOf, nodeCanonicalPayload } from './envelope-signing.js'

const textEncoder = new TextEncoder()

/**
 * 用发送方**那一版** Falcon 公钥验一封信封的签名。
 *
 * @param {{provider?: object, envelope: object, signatureB64: string,
 *          senderFalconPublicKeyHex: string}} params
 *   `senderFalconPublicKeyHex` 必须是小写 hex（与浏览器密钥库同形）——
 *   服务端 `node_session_versions` 已经把它归一到这个形状；拿没归一的
 *   base64 传进来会在 `fromHex` 里静默解析成错字节（b64 的字符集包含 hex），
 *   然后验签失败 —— 看起来像伪造。
 * @returns {Promise<{ok: boolean, detail: string}>} 失败**不抛错**：
 *   "验不过"是结论的一种（可能是伪造，也可能是公钥拿错了），不是调用错误。
 */
export async function verifyNodeEnvelope({
  provider = cryptoProvider,
  envelope,
  signatureB64,
  senderFalconPublicKeyHex
}) {
  if (!envelope || typeof envelope !== 'object') {
    return { ok: false, detail: '信封内容为空或不是对象' }
  }
  const signature = String(signatureB64 || envelope.signature || '').trim()
  if (!signature) {
    return { ok: false, detail: '信封没有签名字段（历史信封不带签名）' }
  }
  const publicKey = String(senderFalconPublicKeyHex || '').trim().toLowerCase()
  if (!publicKey) {
    return { ok: false, detail: '发送方的 Falcon 公钥不可用（无法验收）' }
  }
  try {
    // 附加格式的签名是 base64（发送方签完 `bytesToB64` 存的），
    // 而 `verify` 只收 hex/字节 —— 转换走 provider 的那一个函数。
    const ok = await provider.verify(
      'FALCON',
      publicKey,
      fromHex(b64ToHex(signature)),
      nodeCanonicalPayload(envelope)
    )
    return ok
      ? { ok: true, detail: '签名有效：内容未被改动，且确实来自该发送节点' }
      : { ok: false, detail: '签名无效：信封可能被伪造或篡改，或公钥版本不对' }
  } catch (error) {
    return { ok: false, detail: `验签过程出错（按失败处理）：${error?.message || error}` }
  }
}

/**
 * 用本机那把私钥解出信封里的 SM4 载荷密钥（16 字节）。
 *
 * ⚠️ 抛错而不是返回 null：解不开的原因（本机没有这把私钥 / 密文坏了 /
 *    版本选错）需要原样带给页面，而"返回 null"会把它们混成一句
 *    "解封失败"，用户不知道该做什么。
 */
export async function unwrapNodeEnvelope({ provider = cryptoProvider, keyRef, envelope }) {
  const key = await provider.unwrapEnvelope(
    envelope?.wrapping_algorithm || 'kyber_kem', keyRef, envelope
  )
  const bytes = toBytes(key)
  if (!bytes || bytes.length !== 16) {
    throw new Error(`解出的载荷密钥不是 16 字节 SM4（收到 ${bytes ? `${bytes.length} 字节` : '非字节'}）`)
  }
  return bytes
}

/**
 * 解出 K 之后的自查：`sha256(K)` 必须与信封里 `key_hash` 逐字相同。
 *
 * 这是"解出来了但解错了一把"的唯一当场判据。没有它，错误会推迟到
 * 双方 proof 比对失败时才暴露 —— 而那时的现象（两边证明不一致）
 * 看起来像对方的问题。
 */
export async function checkRecoveredKeyHash(payloadKey, envelope) {
  const declared = String(envelope?.key_hash || '').trim().toLowerCase()
  if (!declared) {
    return { ok: false, detail: '信封没有 key_hash 声明，无法自查解出来的密钥' }
  }
  const actual = await keyHashOf(payloadKey)
  return actual === declared
    ? { ok: true, detail: '解出的密钥与发送方声明的一致（sha256 相同）', hash: actual }
    : { ok: false, detail: `解出的密钥与发送方声明的不一致：本机 ${actual.slice(0, 16)}… ≠ 信封 ${declared.slice(0, 16)}…` }
}

/**
 * 持有证明：`HMAC-SHA256(K, session_id)`（十六进制）。
 *
 * 与服务端 `node_session_confirm` 的口径**必须逐字节一致**：
 * 消息是会话 ID 的 UTF-8 字节，`HMAC` 用 SHA-256，输出 hex。
 * 用 `crypto.subtle` 的 HMAC 而不是 `sha256(K‖msg)` —— 后者不是 HMAC，
 * 而两边一旦实现不同，症状是"双方证明不一致"，看起来像有一方拿错了 K。
 */
export async function nodeProof({ payloadKey, sessionId }) {
  const key = toBytes(payloadKey)
  if (!key) {
    throw new Error('nodeProof：载荷密钥不是字节串')
  }
  const hmacKey = await crypto.subtle.importKey(
    'raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  )
  const signature = await crypto.subtle.sign('HMAC', hmacKey, textEncoder.encode(String(sessionId)))
  return toHex(new Uint8Array(signature))
}

/**
 * 从**本地会话密钥库**取 K 并算持有证明（KMS-012）。
 *
 * 这是"确认"按钮两侧共用的那一段：接收方解封后、发送方分发后都把 K 存进了
 * 本地会话密钥库（`sealSessionSecret`），确认时在这里取出来算 HMAC ——
 * K 从不经过网络，服务端只收到 proof。
 *
 * ⚠️ 本机没有该会话的密钥时**抛错而不是返回空串**：那是"换过设备"这类
 *    真实处境，页面要如实告诉用户回原设备处理，而不是提交一个必然对不上的
 *    证明、让对方看到"证明不一致"（看起来像对方有问题）。
 */
export async function sessionProofFromStore(sessionId) {
  const { unsealSessionSecret } = await import('./node-key-store.js')
  const payloadKey = await unsealSessionSecret(sessionId)
  return nodeProof({ payloadKey, sessionId })
}
