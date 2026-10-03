/**
 * 节点到节点分发的**信封组装与签名**（KMS-009）。
 *
 * 它解决的问题
 * ------------
 * KMS-008 之前，SM4 由**服务端**生成、由服务端用接收方公钥封装（那是过渡实现）。
 * KMS-009 把这两步搬到节点侧：发送节点在浏览器里生成 SM4、用接收方的
 * **指定版本公钥**封装（`provider.wrapForPeer`）、再用**本地 Falcon 私钥**签名，
 * 然后把成品交给服务端登记。服务端从此拿不到明文载荷密钥
 * （计划 §2.1「服务端禁止接收或返回新节点的长期私钥和 SM4 明文」）。
 *
 * 本文件只做**协议层**：规范化字节串、摘要、签名组装、批次号。
 * 密码学原语（KEM/信封加密、Falcon 签名）在 `crypto provider` 里 ——
 * 那正是计划 §13 对 KMS-009 写的位置。
 *
 * 签名覆盖什么（这份规范**必须与服务端逐字节一致**）
 * ------------------------------------------------
 * 字段集合 = `NODE_ENVELOPE_SIGNED_FIELDS`（服务端 `envelope_signature.py` 里那份），
 * 序列化 = **键排序 + 无空白**的紧凑 JSON。
 * 两边任何一处不同，表现都是"节点签的信服务端验不过"——看起来完全像伪造，
 * 所以验收脚本里有一条**跨语言**断言逐字节比对两侧的规范串。
 *
 * ⚠️ 签名要覆盖 `batchId` 与 `expiresAt`，它们就必须在**签名之前**确定 ——
 *    这正是 KMS-009 把两者从"服务端赋值"改成"由页面给出、服务端校验"的原因。
 */
import { bytesToB64, toHex, toBytes } from './browser-provider.js'

/** 与服务端 `envelope_signature.NODE_ENVELOPE_SIGNED_FIELDS` **逐字相同**。 */
export const NODE_ENVELOPE_SIGNED_FIELDS = [
  'batch_id',
  'sender_node_id',
  'receiver_node_id',
  'wrapping_algorithm',
  'payload_algorithm',
  'recipient_key_id',
  'recipient_key_version',
  'key_hash',
  'ciphertext_digest',
  'expires_at'
]

const textEncoder = new TextEncoder()

/**
 * 排序 + 无空白的紧凑 JSON —— 与服务端 `json.dumps(..., sort_keys=True,
 * separators=(',', ':'), ensure_ascii=False)` 同口径。
 *
 * ⚠️ JS 的 `JSON.stringify` 按**插入顺序**输出属性，`sort_keys` 必须自己做。
 *    漏掉排序不会报错：服务端重建出的字节串与签名时那份不同，
 *    表现为"节点签的信服务端验不过"。
 */
export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`
  }
  const keys = Object.keys(value).sort()
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`
}

/**
 * 待签字节串（服务端 `node_canonical_payload` 的对应物）。
 *
 * ⚠️ 缺失字段记为 `null` 而不是跳过 —— 与服务端 `envelope.get(k)` 对齐。
 *    跳过会让"攻击者删掉某字段"与"该字段本就为空"产生同样的字节串。
 *    （JS 的 `JSON.stringify(undefined)` 返回 `undefined` 而不是合法 JSON，
 *     所以这里必须先把 undefined 归一到 null。）
 */
export function nodeCanonicalPayload(envelope) {
  const subset = {}
  for (const key of NODE_ENVELOPE_SIGNED_FIELDS) {
    subset[key] = envelope?.[key] === undefined ? null : envelope[key]
  }
  return textEncoder.encode(canonicalJson(subset))
}

/** 内层信封（含密文）的 SHA256 —— 与服务端 `ciphertext_digest` 同一判据。 */
export async function ciphertextDigest(innerEnvelopeJson) {
  const bytes = textEncoder.encode(String(innerEnvelopeJson || ''))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return toHex(new Uint8Array(digest))
}

/**
 * 载荷密钥的 SHA256（hex）—— 与 `key_hash` 的既有口径一致
 * （服务端 `hashlib.sha256(payload_key).hexdigest()`）。
 *
 * 它的用途是**接收方解出 K 之后自查**：解出来的那把是不是发送方声称的那把。
 * 服务端不存 K，所以服务端无法验证这个值 —— 它只是随信封传递的声明。
 */
export async function keyHashOf(payloadKey) {
  const digest = await crypto.subtle.digest('SHA-256', toBytes(payloadKey))
  return toHex(new Uint8Array(digest))
}

/**
 * 生成一把 16 字节 SM4 载荷密钥（计划 §7 阶段 3「发送节点本地生成 SM4 会话密钥」）。
 */
export function generatePayloadKey() {
  return crypto.getRandomValues(new Uint8Array(16))
}

/**
 * 生成批次号。
 *
 * ⚠️ 由**页面**生成（KMS-009 起），因为签名要覆盖它 —— 服务端事后再赋值的话，
 *    节点签的就是一份"还不知道自己属于哪个批次"的信。服务端会校验格式与唯一性
 *    （`DistributionBatch.batch_id` 上有唯一约束），所以这里只需保证形状一致：
 *    `dist-<yyyyMMddHHmmss>-<8位十六进制>`，与 KMS-008 之前服务端用的同一形状。
 */
export function newBatchId(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`
    + `${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
  const random = crypto.getRandomValues(new Uint8Array(4))
  return `dist-${stamp}-${toHex(random)}`
}

/**
 * 组装完整的分发信封：内层密文 + 待签字段，并算出密文摘要。
 *
 * ⚠️ `ciphertext_digest` 算的是**内层信封**（只有密文那几项）的紧凑 JSON，
 *    而不是整个待签对象的 JSON —— 后者包含摘要自身，是一个自指。
 *    这个坑服务端 `envelope_signature.py` 已经写明（"自己签的信自己验不过"），
 *    这里沿用同一解法，且两侧的序列化口径必须一致。
 *
 * @returns {Promise<{envelope: object, inner: object, innerJson: string, digest: string, keyHash: string, wrapping: string}>}
 */
export async function buildNodeEnvelope({
  provider, payloadKey, wrapping, recipientPublicKeyHex, batchId,
  senderNodeId, receiverNodeId, recipientKeyId, recipientKeyVersion, expiresAt
}) {
  const { envelope: inner, wrapping: wrappingSpelling } = await provider.wrapForPeer(
    wrapping, recipientPublicKeyHex, payloadKey
  )
  const innerJson = canonicalJson(inner)
  const digest = await ciphertextDigest(innerJson)
  const keyHash = await keyHashOf(payloadKey)

  const envelope = {
    ...inner,
    batch_id: batchId,
    sender_node_id: senderNodeId,
    receiver_node_id: receiverNodeId,
    recipient_key_id: recipientKeyId,
    recipient_key_version: Number(recipientKeyVersion),
    key_hash: keyHash,
    ciphertext_digest: digest,
    expires_at: expiresAt
  }
  return { envelope, inner, innerJson, digest, keyHash, wrapping: wrappingSpelling }
}

/**
 * 用本地 Falcon 私钥签这份信封，返回 base64 签名（附加格式）。
 *
 * ⚠️ 用 `provider.sign`（内部走 `falcon512.attached.seal`）而**不是**自己拼
 *    `sig‖msg` —— 服务端参考实现的布局是 `[签名长度2B]‖nonce(40B)‖消息‖签名`，
 *    自己拼必然拼错，而现象只是服务端 `crypto_sign_open` 返回 -1（"验签失败"），
 *    完全看不出是格式问题。这个坑 `browser-provider.js` 里写着实测记录。
 */
export async function signNodeEnvelope(provider, falconKeyRef, envelope) {
  const message = nodeCanonicalPayload(envelope)
  return bytesToB64(await provider.sign('FALCON', falconKeyRef, message))
}