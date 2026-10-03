/**
 * 设备认证凭据（文档 §3.1 激活 / §5 登录）。
 *
 * 这是什么
 * --------
 * 每个节点在该浏览器里有一把**独立的** ECDSA P-256 密钥对：
 *
 *     NodeKeyStore
 *     ├─ Node-001 ── node-Node-001-device-auth   ← 只有 Node-001 用
 *     ├─ Node-002 ── node-Node-002-device-auth   ← 只有 Node-002 用
 *     └─ Node-003 ── ...
 *
 * 私钥用 `generateKey(..., extractable = false)` 生成，**不可导出**，
 * 以 CryptoKey 对象形式直接落在 IndexedDB（由 `node-key-store.js` 所有）。
 * 它只用于一件事：**对服务端下发的挑战签名**，证明"我还是当初激活的那台设备"。
 *
 * 它**不**参与 SM4 分发、Kyber 封装、Falcon 业务签名或 SM2/SSCL 无证书生成
 * （文档 §3.1 明确划开了这条界）。
 *
 * 为什么不是"一个浏览器 = 一个节点"
 * --------------------------------
 * 文档 §4：一个浏览器是**一个节点本地测试环境**，可托管多个互不干扰的节点身份。
 * 所以设备凭据按**节点**分，不是按浏览器分 —— 这正是它与
 * `node-key-store.getDeviceId()`（浏览器级单例、明文比对、服务端无法验证）的区别。
 *
 * ⚠️ 边界（与 node-key-store.js 同一句）：不可导出防的是「密钥被带走」，
 *    不是「密钥被使用」。同源 XSS 在页面内仍可调用 signChallenge() 完成签名。
 *    纯浏览器方案消除不了这一点，留给节点本地 Agent / TPM 的位置见 CryptoProvider 抽象。
 */

import {
  getDevicePrivateKey,
  getDevicePublicKey,
  listDeviceKeyRefs,
  putDeviceKeyPair,
  removeDeviceKeyPair,
  removeSecret,
  sealSecret,
  unsealSecret,
} from './node-key-store.js'
// KMS-003：设备引用的格式（`node-{id}-device-auth` / `...-pub`）与算法常量
// 统一由 key-ref.js 定义 —— 本模块不再各存一份，避免两边定义漂移。
import { DEVICE_AUTH_ALGORITHM, DEVICE_PUB_SUFFIX, buildDeviceRef, parseDeviceRef } from './key-ref.js'

/**
 * 与 `node_auth_views.DEVICE_AUTH_ALGORITHM` 必须一致，改一处要改两处。
 * 定义已收口到 key-ref.js；这里保留同名导出，`store/modules/user.js` 仍在用。
 */
export { DEVICE_AUTH_ALGORITHM }

/** 每个节点的设备凭据 keyRef。格式由 key-ref.js 定义（`node-{id}-device-auth`）。 */
export function deviceKeyRef(nodeId) {
  // ⚠️ 这个字符串**逐字节**决定已激活的浏览器能否登录 ——
  //    已激活设备存的、登录时找的都是它，差一个字符 = 所有老设备登录不上。
  //    所以只委托格式模块，本文件绝不自己拼。
  return buildDeviceRef(nodeId)
}

/**
 * 取（不存在则生成）某节点的设备认证密钥对。
 *
 * @param {string} nodeId
 * @returns {Promise<{publicKeyJwk: object, created: boolean}>}
 */
export async function ensureDeviceKey(nodeId) {
  if (!globalThis.crypto?.subtle) {
    throw new Error('当前环境不支持 WebCrypto，无法生成设备认证密钥')
  }
  const keyRef = deviceKeyRef(nodeId)

  const existing = await getDevicePrivateKey(keyRef)
  if (existing) {
    return { publicKeyJwk: await getDevicePublicKeyJwk(nodeId), created: false }
  }

  const keyPair = await crypto.subtle.generateKey(
    { name: 'ECDSA', namedCurve: 'P-256' },
    // ⚠️ 私钥不可导出是这个模块存在的理由 —— 不要"为了方便调试"改成 true。
    //    一旦可导出，同源脚本就能把设备身份带走，在别的机器上冒充该节点。
    //    `extractable` 只对**私钥**生效（公钥本来就是公开量）。
    false,
    ['sign', 'verify'],
  )

  await putDeviceKeyPair(keyRef, keyPair)
  const publicKeyJwk = await crypto.subtle.exportKey('jwk', keyPair.publicKey)
  await storePublicJwk(keyRef, publicKeyJwk)

  return { publicKeyJwk, created: true }
}

/** 取已存在的设备私钥（CryptoKey）；没有返回 null。 */
export async function getDeviceKey(nodeId) {
  try {
    return await getDevicePrivateKey(deviceKeyRef(nodeId))
  } catch {
    return null
  }
}

/**
 * 本机是否持有该节点的设备凭据（= 是否在本机激活过）。
 *
 * 判据是"私钥**在且能用**"，不是"有记录" —— 后者会把
 * "记录损坏/保护密钥换了"的残状态也算成已激活，而那种状态恰恰需要重新激活。
 */
export async function hasDeviceKey(nodeId) {
  try {
    return (await getDevicePrivateKey(deviceKeyRef(nodeId))) != null
  } catch {
    return false
  }
}

/**
 * 用该节点的设备私钥对挑战签名。
 *
 * 服务端期望 WebCrypto ECDSA 的 **raw r||s（64 字节）**，而 `crypto.subtle.sign`
 * 默认就产出这个格式 —— 所以**不要**再转 DER：服务端是按 raw 拆 (r,s) 的
 * （见 `node_auth_views.verify_device_signature`）。
 *
 * @returns {Promise<string>} base64 编码的签名
 */
export async function signChallenge(nodeId, challenge) {
  const privateKey = await getDeviceKey(nodeId)
  if (!privateKey) {
    throw new Error('本机没有该节点的设备凭据，请先激活')
  }
  const data = new TextEncoder().encode(String(challenge ?? ''))
  const raw = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, privateKey, data)
  return bytesToBase64(new Uint8Array(raw))
}

/**
 * 列出本机**已激活**的节点编号（供登录页的「已激活节点」列表）。
 *
 * 从 `node-{id}-device-auth` 记录里反推节点编号 —— 这条 keyRef 的命名规则
 * 由 `key-ref.js` 定义，这里是唯一需要解析它的地方（用 `parseDeviceRef`）。
 */
export async function listActivatedNodes() {
  try {
    // ⚠️ 必须读 `deviceKeys` store（`listDeviceKeyRefs`），不是 `listSecrets`。
    //    设备私钥是 CryptoKey 对象、存在另一个 object store 里；
    //    用 listSecrets 会漏掉它，结果是**列表恒为空**且不报任何错 ——
    //    2026-09-30 实测踩到：激活明明成功（deviceKeys 里有记录），
    //    登录页却显示"本机还没有已激活的节点"。
    const refs = await listDeviceKeyRefs()
    const ids = new Set()
    for (const ref of refs) {
      // 用格式模块解析，等价于原来的 /^node-(.+)-device-auth$/：
      // `pub === true` 的是 `...-device-auth-pub`（公钥副本），不是设备身份本身，跳过。
      const parsed = parseDeviceRef(ref)
      if (parsed && !parsed.pub) ids.add(parsed.nodeId)
    }
    const out = []
    for (const id of ids) {
      // 逐个确认私钥真的能用（"有记录 ≠ 能用"）
      if (await hasDeviceKey(id)) out.push(id)
    }
    return out.sort()
  } catch {
    // 环境不支持 IndexedDB / WebCrypto 时如实返回空表，
    // 让调用方提示"本机密钥库不可用"，而不是抛出去把登录页搞白屏。
    return []
  }
}

/** 取设备公钥的 JWK；不存在返回 null。 */
export async function getDevicePublicKeyJwk(nodeId) {
  try {
    const keyRef = deviceKeyRef(nodeId)
    // 优先读明文那份（不解封就能拿）
    const stored = await readPublicJwk(keyRef)
    if (stored) return stored
    // 退路：直接从 CryptoKey 导出。走这条说明明文那份丢了，
    // 但私钥还在，仍然可用 —— 顺手补写回去。
    const publicKey = await getDevicePublicKey(keyRef)
    if (!publicKey) return null
    const jwk = await crypto.subtle.exportKey('jwk', publicKey)
    await storePublicJwk(keyRef, jwk)
    return jwk
  } catch {
    return null
  }
}

/**
 * 删除某节点的设备凭据（**只清本地**）。
 *
 * ⚠️ 服务端登记的公钥仍在，所以该节点在此设备上会变成"已登记设备、本机无凭据"
 *    —— 正是文档 §6 描述的"新设备"情形，需要管理员重新签发激活凭证。
 *    这是正确的语义，不要在这边偷偷去改服务端。
 */
export async function removeDeviceKey(nodeId) {
  const keyRef = deviceKeyRef(nodeId)
  await removeDeviceKeyPair(keyRef)
  try {
    await removeSecret(keyRef + DEVICE_PUB_SUFFIX)
  } catch {
    // 已经不存在也算删成功 —— 幂等
  }
}

// ---------------------------------------------------------------------------
// 设备公钥 JWK 的存读（公开量，明文存）
// ---------------------------------------------------------------------------
// 为什么不复用 deviceKeys store：那里放的是 CryptoKey **对象**，读出来不能直接
// 当 JWK 用；而登录/激活都需要把 JWK 发给服务端。所以另存一份序列化后的公开量。
//
// 借 keys store 的记录形状（keyRef/algorithm/publicKey/secret）而不是新开一个
// object store —— 少一个 store 就少一处 schema 变更要同步到 node-key-store
// （它是这座库的唯一 schema 所有者，见那里的 DB_VERSION 注释）。

async function storePublicJwk(keyRef, jwk) {
  await sealSecret(keyRef + DEVICE_PUB_SUFFIX, {
    algorithm: DEVICE_AUTH_ALGORITHM,
    // 公开量：放进 secret 字段只是为了让记录形状与其它记录一致，
    // 它本身没有任何保密要求（JWK 本来就是发给服务端的那份）。
    secret: JSON.stringify(jwk),
    publicKey: JSON.stringify(jwk),
  })
}

async function readPublicJwk(keyRef) {
  try {
    const sealed = await unsealSecret(keyRef + DEVICE_PUB_SUFFIX)
    // ⚠️ 原来这里写的是 `typeof sealed?.secret === 'string' ? sealed.secret : ''`，
    //    但 `unsealSecret` 返回的是**明文 Uint8Array**，不是 `{secret}` 记录对象 ——
    //    该条件永远为假，于是"明文那份"永远读不回来，一直靠
    //    `getDevicePublicKeyJwk` 从 CryptoKey 重新导出的兜底路径才没坏。
    //    现在按字节解码再 JSON.parse；解析失败说明记录不是 JWK，退回 null 走兜底。
    const text = new TextDecoder().decode(sealed)
    return JSON.parse(text)
  } catch {
    return null
  }
}

/**
 * 设备公钥指纹。
 *
 * ⚠️ 必须与 `node_auth_views._public_key_fingerprint` **逐字节一致**：
 *    激活时服务端把指纹写进 `Node.key_device_id`，之后节点登记四套基础公钥时
 *    `store_node_public_key` 会拿传上来的值与它比对，不一致就报"设备不一致"。
 *    所以这里的拼接格式不能随手改 —— 改一处必须同时改服务端那处。
 *    （服务端那边的函数注释里也写明了这条对应关系。）
 *
 * 它是**公开量**（由公钥算出），不构成秘密，只用于"这是不是同一台设备"的识别。
 */
export async function deviceFingerprint(nodeId) {
  const jwk = await getDevicePublicKeyJwk(nodeId)
  if (!jwk) return ''
  const raw = `${jwk.crv || ''}|${jwk.x || ''}|${jwk.y || ''}`
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
  return hex.slice(0, 32)
}

function bytesToBase64(bytes) {
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary)
}