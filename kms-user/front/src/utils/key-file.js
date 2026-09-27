/**
 * 用户密钥文件：`d_a` 的导出 / 导入（计划 §7 P3 步骤 0b）
 * =============================================================================
 * 为什么需要它
 * ------------
 * 用户要能解开分发过来的对称密钥信封，就必须持有**该密钥自己的** `d_a`
 * （= 客户端本地份额 `u` + 服务端 KGC 分片 `t_A`）。
 *
 * 而现状是：本地份额 `u` 由浏览器在每次页面刷新时重新生成、**从不持久化**，
 * 服务端也只存 KGC 分片。因此用户若没有当场把弹出的 `d_a` 抄下来，
 * 这把密钥对"解密"而言就永久失效了（存量那批密钥正是如此，见计划 §8.1.3）。
 *
 * 光靠"弹窗让你自己复制"不可靠。本模块把 `d_a` 落成一个**带校验和的密钥文件**：
 * 用户下载后自行保存，需要解密时再导入回来。
 *
 * ⚠️ 安全边界（必须清楚）
 * ----------------------
 * 1. 校验和是**完整性校验**，不是真实性证明 —— 它只能发现文件被截断/手改，
 *    不能证明文件来自可信方（没有秘密参与，任何人都能重算校验和）。
 * 2. `private_share` 目前是**明文**保存在文件里。后续增强是用用户口令派生密钥
 *    对它加密（见计划 §7 P3 步骤 0b 的"后续增强"）。
 * 3. 本模块产生的任何内容**都不得发给服务端**。服务端只保存 KGC 分片与公开信息；
 *    一旦 `private_share` 出现在出站请求体里，"用户私钥不出客户端"这条不变量即失效
 *    （计划里的 R1' 红线，有回归用例守着）。
 */

export const KEY_FILE_VERSION = 1
export const KEY_FILE_KIND = 'kms-user-key'

/** 参与校验和计算的字段，顺序即规范化顺序（改动会破坏旧文件的校验和） */
const CHECKSUM_FIELDS = ['version', 'kind', 'key_id', 'user_id', 'algorithm', 'created_at', 'private_share', 'public_key']

/**
 * 规范化序列化：只取参与校验的字段、按固定顺序、紧凑 JSON。
 *
 * 之所以要"规范化"而不是直接 JSON.stringify 整个对象：字段顺序、缩进、
 * 以及日后新增字段都会影响结果，导致同一份密钥换台机器就校验不过。
 */
function canonicalize(payload) {
  const ordered = {}
  for (const field of CHECKSUM_FIELDS) {
    ordered[field] = payload[field] === undefined || payload[field] === null ? '' : String(payload[field])
  }
  return JSON.stringify(ordered)
}

/** SHA-256（浏览器 WebCrypto）。返回 `sha256:<hex>` */
export async function computeChecksum(payload) {
  const data = new TextEncoder().encode(canonicalize(payload))
  const digest = await crypto.subtle.digest('SHA-256', data)
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `sha256:${hex}`
}

const HEX64 = /^[0-9a-fA-F]{64}$/
const POINT130 = /^04[0-9a-fA-F]{128}$/

function requireMatch(value, pattern, label) {
  if (typeof value !== 'string' || !pattern.test(value)) {
    throw new Error(`${label} 格式非法`)
  }
  return value.toLowerCase()
}

/**
 * 生成密钥文件内容。
 *
 * @param {object} input
 * @param {string|number} input.keyId      密钥记录 ID（必须记下来 —— 导入时要靠它认领）
 * @param {string|number} input.userId     属主用户 ID
 * @param {string} input.algorithm         算法名（SM2 / SSCL）
 * @param {string} input.privateShare      `d_a`，64 位十六进制
 * @param {string} [input.publicKey]       `P_A`，130 位十六进制（强烈建议带上）
 */
export async function buildKeyFile({ keyId, userId, algorithm, privateShare, publicKey }) {
  if (keyId === undefined || keyId === null || String(keyId).trim() === '') {
    throw new Error('缺少 key_id：密钥文件必须能对应回是哪一条密钥记录')
  }
  if (userId === undefined || userId === null || String(userId).trim() === '') {
    throw new Error('缺少 user_id')
  }
  const payload = {
    version: KEY_FILE_VERSION,
    kind: KEY_FILE_KIND,
    key_id: String(keyId).trim(),
    user_id: String(userId).trim(),
    algorithm: String(algorithm || '').trim().toUpperCase(),
    created_at: new Date().toISOString(),
    private_share: requireMatch(privateShare, HEX64, '私钥份额 private_share'),
    // P_A 不是秘密（它等于 d_a·G），带上它才能在导入时核对
    // "这份私钥确实对应记录里的那把公钥"，避免导入错文件后静默用错密钥。
    public_key: publicKey ? requireMatch(publicKey, POINT130, '公钥 public_key') : ''
  }
  return { ...payload, checksum: await computeChecksum(payload) }
}

/** 把密钥文件序列化成可下载的文本（缩进便于人工查看） */
export function serializeKeyFile(keyFile) {
  return JSON.stringify(keyFile, null, 2)
}

/**
 * 解析并校验一个密钥文件。
 *
 * 校验不通过一律**抛错**，绝不"尽力而为"地返回部分内容 ——
 * 用一个错的密钥去解密，比明确失败危险得多。
 */
export async function parseKeyFile(text) {
  let parsed
  try {
    parsed = typeof text === 'string' ? JSON.parse(text) : text
  } catch (error) {
    throw new Error(`密钥文件不是合法 JSON：${error.message}`)
  }
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('密钥文件内容为空或格式错误')
  }
  if (parsed.kind && parsed.kind !== KEY_FILE_KIND) {
    throw new Error(`这不是本系统的密钥文件（kind=${parsed.kind}）`)
  }
  if (Number(parsed.version) !== KEY_FILE_VERSION) {
    throw new Error(`密钥文件版本不支持：${parsed.version}（当前支持 ${KEY_FILE_VERSION}）`)
  }
  if (!parsed.checksum) {
    throw new Error('密钥文件缺少校验和，无法确认是否被改动过')
  }
  const expected = await computeChecksum(parsed)
  if (String(parsed.checksum).toLowerCase() !== expected.toLowerCase()) {
    throw new Error(
      '密钥文件校验和不匹配：文件可能被改动或截断。' +
        '请使用最初导出的原文件，不要手工编辑。'
    )
  }
  // 校验和过了再校验字段格式（顺序很重要：先证明文件完整，再谈内容是否可用）
  requireMatch(parsed.private_share, HEX64, '私钥份额 private_share')
  if (parsed.public_key) {
    requireMatch(parsed.public_key, POINT130, '公钥 public_key')
  }
  return { ...parsed, private_share: parsed.private_share.toLowerCase(), public_key: (parsed.public_key || '').toLowerCase() }
}

/** 建议的下载文件名 */
export function suggestFileName(keyFile) {
  const stamp = String(keyFile.created_at || '').replace(/[:.]/g, '-').slice(0, 19)
  return `kms-key-${keyFile.key_id}-${keyFile.algorithm || 'key'}-${stamp}.json`
}
