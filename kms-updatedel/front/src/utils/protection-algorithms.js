export const PROTECTION_LABELS = Object.freeze({
  KYBER: '改进型双份额密钥封装（实验版 v1）',
  FALCON_CL_V1: '改进型无证书格加密（实验版 v1）',
  SM2: 'SM2', SSCL: 'SSCL'
})

export function protectionLabel(value) {
  const aliases = { kyber_kem: 'KYBER', falcon_cl_v1: 'FALCON_CL_V1', gm_sm2: 'SM2', gm_sscl: 'SSCL' }
  return PROTECTION_LABELS[aliases[value] || value] || value || '—'
}

export function falconRecipientState({ enabled, receiverNodeCode, keys, loading = false }) {
  const available = enabled && keys.some(key => key.algorithm === 'FALCON_CL_V1' &&
    key.purpose === 'ENCRYPT' && key.materialVersion === 1 && key.allowsNewWork === true && Boolean(key.publicKey))
  const message = !enabled ? '格加密功能尚未启用。' : !receiverNodeCode ? '请先选择接收节点。'
    : loading ? '正在读取接收方密钥…' : available ? `接收节点 ${receiverNodeCode} 的格加密密钥已就绪。`
      : `接收节点 ${receiverNodeCode} 尚无可用的改进型格加密密钥。请在该节点补充后，点击“刷新接收方密钥”。`
  return { available, message }
}
