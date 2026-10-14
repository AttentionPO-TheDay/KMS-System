import { parseMaterial } from './crypto/falcon-cl-v1.js'

/** Labels never establish capability: check the independent material contract. */
export async function inspectFalconEncryption({ node, keys, locals, hasKey, validate = parseMaterial }) {
  const registered = keys.filter(key => key.algorithm === 'FALCON_CL_V1')
  const current = registered.find(key => key.allowsNewWork === true)
  let verified = false
  if (current?.purpose === 'ENCRYPT' && current.materialVersion === 1 &&
      current.generation?.schemeId === 'KMS_SPLIT_FALCON_CL_V1' && current.generation?.schemeVersion === 1) {
    try { validate(current.publicKey, 'PUBLIC', node.nodeId); verified = true } catch {}
  }
  const local = current && locals.find(key => key.algorithm === 'FALCON_CL_V1' &&
    key.keyId === current.keyId && Number(key.version) === Number(current.keyVersion) && key.publicKey === current.publicKey)
  const ready = Boolean(verified && local && await hasKey(local.keyRef))
  const enabled = node.falconClCapability?.enabled === true
  const canAdd = node.status === 'ACTIVE' && enabled && registered.length === 0
  const pending = locals.some(key => key.algorithm === 'FALCON_CL_V1')
  const message = ready ? '已确认改进型格加密材料，本机与登记版本一致。'
    : registered.length ? (verified ? '已登记改进版加密密钥，本机材料缺失或不匹配，请恢复原材料。' : '已有加密登记，但用途、来源、材料或状态未通过检查，请检查原记录。')
      : !enabled ? '改进型格加密功能尚未启用。'
        : node.status !== 'ACTIVE' ? '请先完成节点激活。'
          : pending ? '本机存在尚未登记的加密材料，继续操作会复用原材料。'
            : '当前尚无改进型格加密密钥，可补充一套独立加密材料。'
  return { canAdd, ready, registered: registered.length > 0, pending, message }
}
