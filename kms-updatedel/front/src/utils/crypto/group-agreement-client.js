import {
  commitment, confirmationProof, decryptContribution, deriveGroupMaterial,
  encryptContribution, fromHex, hex, newContribution, validateSnapshot
} from './group-agreement.js'

/** One explicit local operation per round. Dependencies allow isolated real-crypto QA. */
export async function advanceAgreement(group, io) {
  await validateSnapshot(group)
  if (Date.parse(group.expiresAt) <= Date.now() || ['failed', 'closed', 'expired'].includes(group.status)) {
    throw new Error('协商已失效，不能继续处理')
  }
  const nodeId = group.selfNodeId
  const member = group.members.find(item => item.nodeId === nodeId)
  if (group.status === 'committing' && !member.committedAt) {
    // Reject before committing if this device cannot participate in every exchange.
    for (const [left, right, sessionId] of group.channels) {
      if (left !== nodeId && right !== nodeId) continue
      const secret = await io.loadSecret(sessionId)
      try { if (secret.length !== 16) throw new Error('本机基础会话密钥长度不合法') }
      finally { secret.fill(0) }
    }
  }
  let state = await io.loadState(group.agreementId, nodeId)
  if (state && state.scopeHash !== group.scopeHash) throw new Error('本地协商记录与参与者范围不一致')
  if (!state) {
    if (member.commitment || group.status !== 'committing') {
      throw new Error('本机没有此前提交的随机贡献，请回原设备处理，或关闭后重新发起')
    }
    const random = newContribution()
    try { state = { scopeHash: group.scopeHash, contribution: hex(random) } }
    finally { random.fill(0) }
    await io.saveState(group.agreementId, nodeId, state)
  }
  const own = fromHex(state.contribution)
  const recovered = new Map([[nodeId, own]])
  let material
  try {
    const ownCommitment = await commitment(group, nodeId, own)
    if (member.commitment && member.commitment !== ownCommitment) throw new Error('本地随机贡献与已提交承诺不一致')
    let response
    if (group.status === 'committing') {
      if (member.committedAt) throw new Error('已提交贡献承诺，等待其他参与者')
      response = await io.post(group.agreementId, 'commit', { commitment: ownCommitment })
    } else if (group.status === 'exchanging') {
      if (member.exchangedAt) throw new Error('已发送贡献密文，等待其他参与者')
      if (!state.packets) {
        const packets = []
        for (const peer of group.members.filter(item => item.nodeId !== nodeId)) {
          const channel = group.channels.find(([a, b]) => (a === nodeId && b === peer.nodeId) || (b === nodeId && a === peer.nodeId))
          const secret = await io.loadSecret(channel[2])
          try { packets.push(await encryptContribution(group, nodeId, peer.nodeId, channel[2], secret, own)) }
          finally { secret.fill(0) }
        }
        state = { ...state, transcriptHash: group.transcriptHash, packets }
        // Persist the same IV/ciphertext for retries after a lost HTTP response.
        await io.saveState(group.agreementId, nodeId, state)
      }
      if (state.transcriptHash !== group.transcriptHash) throw new Error('已封装贡献的协商摘要发生变化')
      response = await io.post(group.agreementId, 'exchange', { packets: state.packets })
    } else if (group.status === 'confirming') {
      if (member.confirmedAt) throw new Error('本节点已确认，等待其他参与者')
      if (!Array.isArray(group.inbox) || group.inbox.length !== group.members.length - 1) throw new Error('尚未收齐贡献密文')
      for (const packet of group.inbox) {
        if (recovered.has(packet.fromNodeId)) throw new Error('贡献包发送者重复或不合法')
        const secret = await io.loadSecret(packet.channelSessionId)
        try { recovered.set(packet.fromNodeId, await decryptContribution(group, nodeId, packet, secret)) }
        finally { secret.fill(0) }
      }
      material = await deriveGroupMaterial(group, recovered)
      const proof = await confirmationProof(group, material.confirmationKey)
      await io.saveKey(group.agreementId, material.key)
      response = await io.post(group.agreementId, 'confirm', { transcriptHash: group.transcriptHash, proof })
    } else {
      throw new Error('当前阶段没有待执行的操作')
    }
    if (response.scopeHash !== group.scopeHash || response.selfNodeId !== nodeId) throw new Error('服务端返回了其他协商的结果')
    await validateSnapshot(response)
    return response
  } finally {
    for (const secret of recovered.values()) secret.fill(0)
    material?.key.fill(0)
    material?.confirmationKey.fill(0)
  }
}
