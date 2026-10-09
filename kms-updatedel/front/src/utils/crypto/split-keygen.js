import { generationScheme, publicGeneration, publicGenerationContext, GENERATION_CONTEXT_FIELDS } from './generation-scheme.js'

const encoder = new TextEncoder()
export const SPLIT_KEYGEN_SALT_TAG = 'KMS-SPLIT-KEYGEN-V1/HKDF-SHA256'
export const SPLIT_KEYGEN_CONTEXT_TAG = 'KMS-SPLIT-KEYGEN-V1/CONTEXT'

export function encodeGenerationContext(input) {
  const context = publicGenerationContext(input)
  const parts = [encoder.encode(SPLIT_KEYGEN_CONTEXT_TAG)]
  for (const field of GENERATION_CONTEXT_FIELDS) {
    const bytes = encoder.encode(context[field])
    const length = new Uint8Array(4)
    new DataView(length.buffer).setUint32(0, bytes.length, false)
    parts.push(length, bytes)
  }
  const out = new Uint8Array(parts.reduce((length, bytes) => length + bytes.length, 0))
  let offset = 0
  for (const bytes of parts) { out.set(bytes, offset); offset += bytes.length }
  return out
}

/** WebCrypto HKDF, deliberately not a handwritten KDF. Caller owns/wipes the two contributions. */
export async function deriveSplitSeed(kgcShare, localSecret, input) {
  if (!(kgcShare instanceof Uint8Array) || kgcShare.length !== 32 || !(localSecret instanceof Uint8Array) || localSecret.length !== 32) {
    throw new Error('双份额生成需要两个独立的 32 字节秘密贡献')
  }
  const context = publicGenerationContext(input)
  const scheme = generationScheme(context.coreFamily)
  const ikm = new Uint8Array(64)
  ikm.set(kgcShare); ikm.set(localSecret, 32)
  try {
    const salt = await crypto.subtle.digest('SHA-256', encoder.encode(SPLIT_KEYGEN_SALT_TAG))
    const key = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits'])
    return new Uint8Array(await crypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt, info: encodeGenerationContext(context) }, key, scheme.seedBytes * 8))
  } finally { ikm.fill(0) } // best effort only: JS/WebCrypto cannot promise complete memory erasure
}

function decodeShare(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9+/]{43}=$/.test(value)) throw new Error('KGC 份额不是规范的 32 字节 base64')
  const bytes = Uint8Array.from(atob(value), character => character.charCodeAt(0))
  if (bytes.length !== 32 || btoa(String.fromCharCode(...bytes)) !== value) { bytes.fill(0); throw new Error('KGC 份额编码不规范') }
  return bytes
}

/** No network dependency: identity headers and issuance transport are supplied by the lifecycle layer. */
export async function issueSplitSeed(request, issueKeygen, expected = {}) {
  if (typeof issueKeygen !== 'function') throw new Error('新后量子密钥必须使用 KGC 双份额发放，禁止普通 KeyGen 降级')
  const scheme = generationScheme(request.algorithm)
  const identityFields = ['nodeId', 'userId', 'bindingKind', 'deviceFingerprint', 'demoSessionId', 'demoRevision']
  if (!expected || typeof expected !== 'object' || identityFields.some(field => !Object.hasOwn(expected, field))) {
    throw new Error('双份额生成必须提供当前可信账号/设备或 Demo 会话的完整公开上下文')
  }
  for (const [field, value] of Object.entries(expected)) {
    if (!GENERATION_CONTEXT_FIELDS.includes(field) || (typeof value !== 'string' && !(typeof value === 'number' && Number.isSafeInteger(value) && value >= 0))) throw new Error('期望生成上下文字段或类型非法')
  }
  if (String(expected.nodeId) !== request.nodeId || !/^(0|[1-9][0-9]*)$/.test(String(expected.userId))) throw new Error('可信账号或节点上下文不匹配')
  if (expected.bindingKind === 'DEVICE') {
    if (!expected.deviceFingerprint || expected.demoSessionId !== '' || expected.demoRevision !== '') throw new Error('可信设备上下文不完整')
  } else if (expected.bindingKind === 'DEMO') {
    if (expected.deviceFingerprint !== '' || !expected.demoSessionId || !/^(0|[1-9][0-9]*)$/.test(String(expected.demoRevision))) throw new Error('可信 Demo 上下文不完整')
  } else throw new Error('未知可信生成绑定类型')
  const localSecret = crypto.getRandomValues(new Uint8Array(32))
  let share
  let issuance
  try {
    issuance = await issueKeygen({ ...request, generationScheme: scheme.schemeId, purpose: scheme.purpose })
    const context = publicGenerationContext(issuance?.context)
    const generation = publicGeneration({ schemeId: issuance.generationScheme, schemeVersion: 1, generationIssuanceId: issuance.generationIssuanceId, authorizationTicketId: issuance.authorizationTicketId })
    const required = { schemeId: scheme.schemeId, schemeVersion: '1', coreFamily: scheme.coreFamily, nodeId: request.nodeId, keyId: request.keyId, keyVersion: String(request.keyVersion), variant: String(request.variant), purpose: scheme.purpose, generationIssuanceId: generation.generationIssuanceId }
    for (const field of Object.keys(expected)) {
      if (context[field] !== String(expected[field])) throw new Error(`KGC 发放上下文与当前可信身份不符：${field}`)
    }
    for (const [field, value] of Object.entries(required)) {
      if (context[field] !== value) throw new Error(`KGC 发放上下文与生成请求不符：${field}`)
    }
    const expiresAt = typeof issuance.expiresAt === 'string' && /(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(issuance.expiresAt) ? Date.parse(issuance.expiresAt) : NaN
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) throw new Error('KGC 生成授权已过期或到期时间无效')
    share = decodeShare(issuance.share)
    return { seed: await deriveSplitSeed(share, localSecret, context), generation, generationContext: context }
  } finally {
    share?.fill(0)
    localSecret.fill(0)
    // The transport response contains an immutable base64 string; drop our reference but cannot wipe strings.
    if (issuance && typeof issuance === 'object') {
      try { delete issuance.share } catch { /* A frozen response can only be released, not cleared. */ }
    }
    issuance = null
  }
}
