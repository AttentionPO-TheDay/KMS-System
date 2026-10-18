// Real WebCrypto + real client round orchestration. In-memory coordinator fixture only.
import assert from 'node:assert/strict'
import {
  GROUP_PROTOCOL, commitment, confirmationProof, decryptContribution, deriveGroupMaterial,
  digest, encryptContribution, hex, newContribution, validateSnapshot
} from '../src/utils/crypto/group-agreement.js'
import { advanceAgreement } from '../src/utils/crypto/group-agreement-client.js'

const ids = ['A', 'B', 'C']
const pair = (a, b) => JSON.stringify([a, b].sort())
const channelSecrets = new Map([['A', 'B'], ['A', 'C'], ['B', 'C']].map(([a, b]) =>
  [`channel-${a}-${b}`, crypto.getRandomValues(new Uint8Array(16))]))

class Coordinator {
  constructor() {
    this.group = {
      protocol: GROUP_PROTOCOL, agreementId: `gka-${crypto.randomUUID()}`,
      initiatorNodeId: 'A', status: 'committing', expiresAt: new Date(Date.now() + 1800000).toISOString(),
      members: ids.map(nodeId => ({ nodeId, name: nodeId, commitment: '', committedAt: null, exchangedAt: null, confirmedAt: null })),
      channels: [['A', 'B', 'channel-A-B'], ['A', 'C', 'channel-A-C'], ['B', 'C', 'channel-B-C']],
      transcriptHash: '', events: [],
    }
    this.packets = new Map(); this.proofs = new Map(); this.requests = []
  }
  async initialize() {
    const g = this.group
    g.scopeHash = await digest([GROUP_PROTOCOL, g.agreementId, ids, g.channels, g.expiresAt])
    return this
  }
  snapshot(nodeId) {
    return structuredClone({ ...this.group, selfNodeId: nodeId,
      inbox: [...this.packets.entries()].flatMap(([fromNodeId, packets]) =>
        packets.filter(packet => packet.toNodeId === nodeId).map(packet => ({ fromNodeId, ...packet }))) })
  }
  async post(nodeId, id, action, payload) {
    assert.equal(id, this.group.agreementId)
    this.requests.push(structuredClone({ nodeId, action, payload }))
    const member = this.group.members.find(item => item.nodeId === nodeId)
    if (action === 'commit') {
      if (member.commitment) assert.equal(member.commitment, payload.commitment)
      member.commitment = payload.commitment; member.committedAt = new Date().toISOString()
      if (this.group.members.every(item => item.committedAt)) {
        this.group.transcriptHash = await digest([this.group.scopeHash, this.group.members.map(item => [item.nodeId, item.commitment])])
        this.group.status = 'exchanging'
      }
    } else if (action === 'exchange') {
      if (member.exchangedAt) assert.deepEqual(this.packets.get(nodeId), payload.packets)
      this.packets.set(nodeId, structuredClone(payload.packets)); member.exchangedAt = new Date().toISOString()
      if (this.group.members.every(item => item.exchangedAt)) this.group.status = 'confirming'
    } else if (action === 'confirm') {
      this.proofs.set(nodeId, payload.proof); member.confirmedAt = new Date().toISOString()
      if (this.group.members.every(item => item.confirmedAt)) {
        this.group.status = new Set(this.proofs.values()).size === 1 ? 'established' : 'failed'
      }
    } else throw Error(action)
    return this.snapshot(nodeId)
  }
}

function participant(server, nodeId) {
  const states = new Map(), keys = new Map()
  return { states, keys, io: {
    loadState: async id => structuredClone(states.get(id) || null),
    saveState: async (id, actor, state) => { assert.equal(actor, nodeId); states.set(id, structuredClone(state)) },
    loadSecret: async id => { assert(channelSecrets.has(id)); return channelSecrets.get(id).slice() },
    saveKey: async (id, key) => keys.set(id, key.slice()),
    post: (...args) => server.post(nodeId, ...args)
  } }
}

const server = await new Coordinator().initialize()
const clients = new Map(ids.map(id => [id, participant(server, id)]))
for (const id of ids) await advanceAgreement(server.snapshot(id), clients.get(id).io)
assert.equal(server.group.status, 'exchanging')
assert.equal(new Set([...clients.values()].map(client => client.states.get(server.group.agreementId).contribution)).size, 3)

// Lost local state must never silently replace a committed contribution.
const lost = participant(server, 'A')
await assert.rejects(advanceAgreement(server.snapshot('A'), lost.io), /此前提交的随机贡献/)
assert.equal(server.requests.length, 3)

// Lost response: immutable encrypted retry must reuse the identical IV and ciphertext.
const initial = server.snapshot('A'), original = clients.get('A').io.post
clients.get('A').io.post = async (...args) => { await original(...args); throw Error('fixture lost response') }
await assert.rejects(advanceAgreement(initial, clients.get('A').io), /lost response/)
clients.get('A').io.post = original
await advanceAgreement(initial, clients.get('A').io)
assert.deepEqual(server.requests[3].payload, server.requests[4].payload)
for (const id of ['B', 'C']) await advanceAgreement(server.snapshot(id), clients.get(id).io)
assert.equal(server.group.status, 'confirming')

// A packet decrypts only in its bound group, direction, channel and commitment.
const snapshotB = server.snapshot('B'), packetA = snapshotB.inbox.find(item => item.fromNodeId === 'A')
const contributionA = await decryptContribution(snapshotB, 'B', packetA, channelSecrets.get('channel-A-B'))
assert.equal(hex(contributionA), clients.get('A').states.get(server.group.agreementId).contribution)
const changed = structuredClone(packetA)
const tampered = Uint8Array.from(atob(changed.ciphertext), c => c.charCodeAt(0)); tampered[0] ^= 1
changed.ciphertext = btoa(String.fromCharCode(...tampered))
await assert.rejects(decryptContribution(snapshotB, 'B', changed, channelSecrets.get('channel-A-B')))
await assert.rejects(decryptContribution(snapshotB, 'C', packetA, channelSecrets.get('channel-A-B')))
await assert.rejects(decryptContribution(snapshotB, 'B', packetA, crypto.getRandomValues(new Uint8Array(16))))
const other = await new Coordinator().initialize()
other.group.members = structuredClone(server.group.members)
other.group.transcriptHash = await digest([other.group.scopeHash, other.group.members.map(item => [item.nodeId, item.commitment])])
await assert.rejects(decryptContribution(other.snapshot('B'), 'B', packetA, channelSecrets.get('channel-A-B')))
const corruptedRoster = server.snapshot('B'); corruptedRoster.members[0].nodeId = 'IMPOSTOR'
await assert.rejects(validateSnapshot(corruptedRoster))
const corruptedCommitment = server.snapshot('B'); corruptedCommitment.members[0].commitment = 'f'.repeat(64)
await assert.rejects(validateSnapshot(corruptedCommitment), /承诺记录被修改/)
const dishonest = newContribution()
const dishonestPacket = await encryptContribution(snapshotB, 'A', 'B', 'channel-A-B', channelSecrets.get('channel-A-B'), dishonest)
await assert.rejects(decryptContribution(snapshotB, 'B', { fromNodeId: 'A', ...dishonestPacket }, channelSecrets.get('channel-A-B')), /承诺不一致/)

const contributions = new Map([...clients].map(([id, client]) => [id, Uint8Array.from(client.states.get(server.group.agreementId).contribution.match(/../g), x => parseInt(x, 16))]))
await assert.rejects(deriveGroupMaterial(server.snapshot('A'), new Map([['A', contributions.get('A')]])), /尚未收齐/)

// Exact same key and domain-separated confirmation for all three real participants.
for (const id of ids) {
  await advanceAgreement(server.snapshot(id), clients.get(id).io)
  if (id !== 'C') assert.equal(server.group.status, 'confirming')
}
assert.equal(server.group.status, 'established')
const finalKeys = [...clients.values()].map(client => hex(client.keys.get(server.group.agreementId)))
assert.equal(new Set(finalKeys).size, 1)
assert.equal(finalKeys[0].length, 32)
assert.equal(new Set(server.proofs.values()).size, 1)

// Changing ANY participant contribution changes the jointly derived key.
const baseline = await deriveGroupMaterial(server.snapshot('A'), contributions)
for (const id of ids) {
  const replacement = newContribution(), modified = new Map(contributions); modified.set(id, replacement)
  const group = server.snapshot('A')
  group.members.find(member => member.nodeId === id).commitment = await commitment(group, id, replacement)
  group.transcriptHash = await digest([group.scopeHash, group.members.map(member => [member.nodeId, member.commitment])])
  const material = await deriveGroupMaterial(group, modified)
  assert.notEqual(hex(material.key), hex(baseline.key))
  assert.notEqual(await confirmationProof(group, material.confirmationKey), [...server.proofs.values()][0])
  material.key.fill(0); material.confirmationKey.fill(0); replacement.fill(0)
}
const payloads = JSON.stringify(server.requests)
for (const client of clients.values()) assert(!payloads.includes(client.states.get(server.group.agreementId).contribution))
assert(server.requests.every(request => !('key' in request.payload) && !('contribution' in request.payload)))
baseline.key.fill(0); baseline.confirmationKey.fill(0); contributionA.fill(0); dishonest.fill(0)
for (const secret of contributions.values()) secret.fill(0)
console.log('PASS: 三节点真实随机贡献/加密交换/共同派生/全员确认；每个贡献影响最终密钥；篡改、重放、缺失贡献、错误通道和本地丢失均拒绝；重试复用密文；不上传明文')
