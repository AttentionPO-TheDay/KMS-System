/** Real contributory establishment over already-confirmed pairwise channels.
 * No MPC, malicious-party security proof or forward-secrecy claim.
 * Pure byte operations; persistence and HTTP deliberately live outside this file.
 */
export const GROUP_PROTOCOL = 'kms-contributory-v1'
const encoder = new TextEncoder()
const encoded = value => encoder.encode(JSON.stringify(value))
export const hex = bytes => Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
export function fromHex(value) {
  if (typeof value !== 'string' || !/^(?:[0-9a-f]{2})+$/.test(value)) throw new Error('十六进制材料不合法')
  return Uint8Array.from(value.match(/../g), byte => parseInt(byte, 16))
}
const b64 = bytes => btoa(String.fromCharCode(...bytes))
function unb64(value, length) {
  if (typeof value !== 'string' || value.length > 128) throw new Error('贡献密文编码不合法')
  const bytes = Uint8Array.from(atob(value), char => char.charCodeAt(0))
  if (bytes.length !== length || b64(bytes) !== value) throw new Error('贡献密文长度或编码不合法')
  return bytes
}
export async function digest(value) {
  if (!globalThis.crypto?.subtle) throw new Error('多方协商需要HTTPS或localhost安全环境，请检查访问地址')
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', encoded(value))))
}

export async function validateSnapshot(group) {
  if (group.protocol !== GROUP_PROTOCOL || !/^gka-[0-9a-f-]{36}$/.test(group.agreementId) ||
      !Array.isArray(group.members) || group.members.length < 3 || group.members.length > 8) {
    throw new Error('多方协商记录不合法')
  }
  const ids = group.members.map(member => member.nodeId)
  if (ids.some(id => typeof id !== 'string' || !id) || new Set(ids).size !== ids.length || !ids.includes(group.selfNodeId)) {
    throw new Error('协商参与者不合法')
  }
  const pairs = new Set()
  if (!Array.isArray(group.channels) || group.channels.length !== ids.length * (ids.length - 1) / 2) {
    throw new Error('基础会话不完整')
  }
  for (const channel of group.channels) {
    if (!Array.isArray(channel) || channel.length !== 3) throw new Error('基础会话记录不合法')
    const [a, b, sid] = channel
    const pair = JSON.stringify([ids.indexOf(a), ids.indexOf(b)].sort((x, y) => x - y))
    if (!ids.includes(a) || !ids.includes(b) || a === b || typeof sid !== 'string' || !sid || pairs.has(pair)) {
      throw new Error('基础会话归属不合法')
    }
    pairs.add(pair)
  }
  const scopeHash = await digest([GROUP_PROTOCOL, group.agreementId, ids, group.channels, group.expiresAt])
  if (scopeHash !== group.scopeHash) throw new Error('参与者或基础会话记录被修改')
  if (group.transcriptHash) {
    if (group.members.some(member => !/^[0-9a-f]{64}$/.test(member.commitment))) throw new Error('贡献承诺不完整')
    const transcriptHash = await digest([scopeHash, group.members.map(member => [member.nodeId, member.commitment])])
    if (transcriptHash !== group.transcriptHash) throw new Error('贡献承诺记录被修改')
  }
}

export function newContribution() { return crypto.getRandomValues(new Uint8Array(32)) }

export async function commitment(group, nodeId, contribution) {
  if (contribution.length !== 32 || !group.members.some(member => member.nodeId === nodeId)) {
    throw new Error('随机贡献长度或归属不合法')
  }
  return digest([group.scopeHash, nodeId, hex(contribution)])
}

async function hkdf(secret, salt, info, length) {
  const material = await crypto.subtle.importKey('raw', secret, 'HKDF', false, ['deriveBits'])
  return new Uint8Array(await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt: fromHex(salt), info: encoded(info) }, material, length * 8
  ))
}

function packetContext(group, sender, recipient, sessionId) {
  if (!/^[0-9a-f]{64}$/.test(group.transcriptHash)) throw new Error('需全员提交承诺后才能交换贡献')
  const channel = group.channels.find(([a, b]) => (a === sender && b === recipient) || (b === sender && a === recipient))
  if (!channel || channel[2] !== sessionId || sender === recipient) throw new Error('贡献包基础会话不匹配')
  return [GROUP_PROTOCOL, 'contribution', group.scopeHash, group.transcriptHash, sender, recipient, sessionId]
}

async function channelKey(group, pairwiseSecret, context) {
  if (pairwiseSecret.length !== 16) throw new Error('基础会话密钥长度不合法')
  const bytes = await hkdf(pairwiseSecret, group.transcriptHash, context, 32)
  try { return await crypto.subtle.importKey('raw', bytes, 'AES-GCM', false, ['encrypt', 'decrypt']) }
  finally { bytes.fill(0) }
}

export async function encryptContribution(group, sender, recipient, sessionId, pairwiseSecret, contribution) {
  if (contribution.length !== 32) throw new Error('随机贡献必须为32字节')
  const context = packetContext(group, sender, recipient, sessionId)
  const key = await channelKey(group, pairwiseSecret, context)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ciphertext = new Uint8Array(await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: encoded(context) }, key, contribution
  ))
  return { toNodeId: recipient, channelSessionId: sessionId, iv: b64(iv), ciphertext: b64(ciphertext) }
}

export async function decryptContribution(group, recipient, packet, pairwiseSecret) {
  if (packet.toNodeId !== recipient) throw new Error('贡献包不属于本节点')
  const context = packetContext(group, packet.fromNodeId, recipient, packet.channelSessionId)
  const key = await channelKey(group, pairwiseSecret, context)
  let contribution
  try {
    contribution = new Uint8Array(await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: unb64(packet.iv, 12), additionalData: encoded(context) }, key,
      unb64(packet.ciphertext, 48)
    ))
  } catch {
    throw new Error('贡献密文认证失败，可能被篡改或基础会话密钥不匹配')
  }
  const expected = group.members.find(member => member.nodeId === packet.fromNodeId)?.commitment
  if (await commitment(group, packet.fromNodeId, contribution) !== expected) {
    contribution.fill(0)
    throw new Error('随机贡献与先前承诺不一致')
  }
  return contribution
}

export async function deriveGroupMaterial(group, contributions) {
  await validateSnapshot(group)
  if (!group.transcriptHash || contributions.size !== group.members.length) throw new Error('尚未收齐全员随机贡献')
  const input = new Uint8Array(group.members.length * 32)
  let key, confirmationKey
  try {
    for (let index = 0; index < group.members.length; index++) {
      const member = group.members[index]
      const contribution = contributions.get(member.nodeId)
      if (!(contribution instanceof Uint8Array) || await commitment(group, member.nodeId, contribution) !== member.commitment) {
        throw new Error('随机贡献缺失或承诺不一致')
      }
      input.set(contribution, index * 32)
    }
    key = await hkdf(input, group.transcriptHash, [GROUP_PROTOCOL, 'group-sm4-key', group.scopeHash], 16)
    confirmationKey = await hkdf(input, group.transcriptHash, [GROUP_PROTOCOL, 'group-confirmation-key', group.scopeHash], 32)
    return { key, confirmationKey }
  } catch (error) {
    key?.fill(0)
    confirmationKey?.fill(0)
    throw error
  } finally { input.fill(0) }
}

export async function confirmationProof(group, confirmationKey) {
  if (confirmationKey.length !== 32) throw new Error('确认密钥长度不合法')
  const key = await crypto.subtle.importKey('raw', confirmationKey, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  return hex(new Uint8Array(await crypto.subtle.sign('HMAC', key,
    encoded([GROUP_PROTOCOL, 'confirm', group.scopeHash, group.transcriptHash])
  )))
}
