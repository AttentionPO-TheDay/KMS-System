import { normalizeAlgorithm } from './provider.js'

export const GENERATION_SCHEMES = Object.freeze({
  KYBER: Object.freeze({ schemeId: 'KMS_SPLIT_KEM_V1', schemeVersion: 1, coreFamily: 'KYBER', purpose: 'KEM_KEYGEN', seedBytes: 64 }),
  FALCON: Object.freeze({ schemeId: 'KMS_SPLIT_SIGN_V1', schemeVersion: 1, coreFamily: 'FALCON', purpose: 'SIGN_KEYGEN', seedBytes: 48 })
})

// Frozen transcript order. Authorization can be renewed; its ID is deliberately NOT in the KDF.
export const GENERATION_CONTEXT_FIELDS = Object.freeze([
  'schemeId', 'schemeVersion', 'coreFamily', 'variant', 'userId', 'nodeId',
  'bindingKind', 'deviceFingerprint', 'demoSessionId', 'demoRevision',
  'keyId', 'keyVersion', 'purpose', 'generationIssuanceId'
])
const NUMERIC_FIELDS = new Set(['schemeVersion', 'userId', 'demoRevision', 'keyVersion'])
const GENERATION_FIELDS = ['schemeId', 'schemeVersion', 'generationIssuanceId', 'authorizationTicketId']

export function generationScheme(algorithm) {
  const scheme = GENERATION_SCHEMES[normalizeAlgorithm(algorithm)]
  if (!scheme) throw new Error('双份额生成只支持 KYBER / FALCON 核心')
  return scheme
}

function knownScheme(id) {
  const scheme = Object.values(GENERATION_SCHEMES).find(value => value.schemeId === id)
  if (!scheme) throw new Error('未知生成方案，禁止降级到普通 KeyGen')
  return scheme
}

function decimal(value, field) {
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value) || value < 0) throw new Error(`生成上下文 ${field} 必须为非负安全整数`)
    return String(value)
  }
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) {
    throw new Error(`生成上下文 ${field} 必须为最短非负十进制字符串`)
  }
  return value
}

function objectFields(input, allowed) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('生成来源必须为对象')
  if (Object.keys(input).some(key => !allowed.includes(key))) throw new Error('生成来源包含非公开或未知字段')
}

/** Explicit public DTO allowlist: never spread an issuance response into pending/registry metadata. */
export function publicGeneration(input) {
  if (input == null) return null // historical keys are not relabelled
  objectFields(input, GENERATION_FIELDS)
  const scheme = knownScheme(input.schemeId)
  if (decimal(input.schemeVersion, 'schemeVersion') !== '1') throw new Error('不支持的生成方案版本')
  for (const field of ['generationIssuanceId', 'authorizationTicketId']) {
    if (typeof input[field] !== 'string' || !input[field]) throw new Error(`生成来源缺少 ${field}`)
  }
  return { schemeId: scheme.schemeId, schemeVersion: 1, generationIssuanceId: input.generationIssuanceId, authorizationTicketId: input.authorizationTicketId }
}

/** Validates and snapshots the exact server-confirmed transcript; identity strings are never trimmed. */
export function publicGenerationContext(input) {
  objectFields(input, GENERATION_CONTEXT_FIELDS)
  const out = {}
  for (const field of GENERATION_CONTEXT_FIELDS) {
    const value = input[field]
    if (field === 'demoRevision' && value === '') out[field] = ''
    else if (NUMERIC_FIELDS.has(field)) out[field] = decimal(value, field)
    else {
      if (typeof value !== 'string') throw new Error(`生成上下文缺少文本字段 ${field}`)
      out[field] = value
    }
  }
  const scheme = knownScheme(out.schemeId)
  if (out.schemeVersion !== '1' || out.coreFamily !== scheme.coreFamily || out.purpose !== scheme.purpose) throw new Error('生成方案、核心或用途不匹配')
  if (!(scheme.coreFamily === 'KYBER' ? ['512', '768', '1024'] : ['512']).includes(out.variant)) throw new Error('不支持的核心参数集')
  if (out.keyVersion === '0' || !out.userId || !out.nodeId || !out.keyId || !out.generationIssuanceId) throw new Error('生成上下文身份、版本或发放引用为空')
  if (out.bindingKind === 'DEVICE') {
    if (!out.deviceFingerprint || out.demoSessionId !== '' || out.demoRevision !== '') throw new Error('设备生成上下文不完整')
  } else if (out.bindingKind === 'DEMO') {
    if (out.deviceFingerprint !== '' || !out.demoSessionId || out.demoRevision === '') throw new Error('Demo 生成上下文不完整')
  } else throw new Error('未知生成绑定类型')
  return out
}

export function formatGenerationName(algorithm, generation = null) {
  const name = normalizeAlgorithm(algorithm)
  if (name !== 'KYBER' && name !== 'FALCON') return name
  const id = typeof generation === 'string' ? generation : generation?.schemeId
  if (!id) return name === 'KYBER' ? '历史兼容 KEM（来源未记录）' : '历史兼容签名（来源未记录）'
  const scheme = knownScheme(id)
  if (scheme.coreFamily !== name) throw new Error('生成方案与核心不匹配')
  return name === 'KYBER' ? '改进型双份额 KEM（实验版 v1）' : '改进型双份额签名（实验版 v1）'
}

export function coreDetail(algorithm, variant = undefined) {
  const name = normalizeAlgorithm(algorithm)
  if (name === 'KYBER') return `CRYSTALS-Kyber round-3 / ${variant || 768}；不是 ML-KEM；KGC 辅助身份绑定 KeyGen 扩展，无形式化无证书安全证明`
  if (name === 'FALCON') return 'Falcon-512 round-3（非 padded）；不是 FN-DSA；仅用于签名，无形式化无证书安全证明'
  return name
}
