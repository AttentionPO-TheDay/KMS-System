// Local IndexedDB ciphertext only. Never include this package in registration/API payloads.
const FORMAT = 'kms-local-encrypted-key-v1'

export function makeEncryptedKeyPackage(iv, ciphertext) {
  if (!(iv instanceof Uint8Array) || iv.byteLength !== 12 ||
      !(ciphertext instanceof ArrayBuffer || ArrayBuffer.isView(ciphertext)) ||
      ciphertext.byteLength < 16) throw new Error('本机加密密钥包格式无效')
  return { format: FORMAT, cipher: 'AES-256-GCM', iv, ciphertext }
}

export function readEncryptedKeyPackage(record) {
  const packet = record.encryptedKeyPackage
  if (packet !== undefined) {
    if (!packet || packet.format !== FORMAT || packet.cipher !== 'AES-256-GCM' ||
        record.iv !== undefined || record.sealed !== undefined) {
      throw new Error('本机加密密钥包格式无效或存在重复密文字段')
    }
    return makeEncryptedKeyPackage(packet.iv, packet.ciphertext)
  }
  // Read old records in place: do not regenerate keys or reseal on lookup.
  return makeEncryptedKeyPackage(record.iv, record.sealed)
}

export function storeEncryptedKeyPackage(record) {
  if (record.algorithm !== 'FALCON_CL_V1') return record
  const packet = makeEncryptedKeyPackage(record.iv, record.sealed)
  const stored = { ...record, encryptedKeyPackage: packet }
  delete stored.iv
  delete stored.sealed
  return stored
}

export function publicKeyRecord(record) {
  const summary = { ...record }
  delete summary.iv
  delete summary.sealed
  delete summary.encryptedKeyPackage
  return summary
}
