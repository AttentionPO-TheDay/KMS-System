import { formatGenerationName, GENERATION_SCHEMES } from './crypto/generation-scheme.js'

// Keep signing and encryption algorithms distinct; never relabel existing keys.
export const PROTECTION_KEY_ALGORITHMS = Object.freeze(['KYBER', 'SSCL', 'SM2', 'FALCON_CL_V1'])
export const SIGNING_KEY_ALGORITHMS = Object.freeze(['FALCON'])

export function generationAlgorithms(purpose) {
  if (purpose === 'protection') return PROTECTION_KEY_ALGORITHMS
  if (purpose === 'signing') return SIGNING_KEY_ALGORITHMS
  throw new Error('未知密钥生成用途')
}

export const GENERATION_ALGORITHM_META = Object.freeze({
  KYBER: { label: formatGenerationName('KYBER', GENERATION_SCHEMES.KYBER), role: '密钥封装（KEM）：保护 SM4 会话密钥，提供抗量子封装能力。' },
  SSCL: { label: 'SSCL', role: '国密无证书：保护 SM4 会话密钥。' },
  SM2: { label: 'SM2', role: '国密：保护 SM4 会话密钥。' },
  FALCON_CL_V1: { label: formatGenerationName('FALCON_CL_V1', GENERATION_SCHEMES.FALCON_CL_V1), role: '改进型 Falcon 格加密：用于分发时保护 SM4 会话密钥，不用于签名；实验性自定义方案，不声明国密合规。' },
  FALCON: { label: '标准 Falcon 会话签名密钥', role: 'Falcon-512 标准签名核心，沿用现有双份额生成流程。用于分发信封签名与验签，不用于封装或加密 SM4 密钥。' }
})
