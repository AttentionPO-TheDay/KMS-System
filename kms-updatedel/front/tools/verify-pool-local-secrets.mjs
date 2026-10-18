// Isolated IndexedDB and actual page handlers. No production API or key material.
import assert from 'node:assert/strict'
import 'fake-indexeddb/auto'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { parse, babelParse } from '@vue/compiler-sfc'
import * as store from '../src/utils/crypto/node-key-store.js'
import { keyHashOf } from '../src/utils/crypto/envelope-signing.js'
import { sessionProofFromStore } from '../src/utils/crypto/node-envelope.js'
import { KEYSTORE_DB_NAME } from '../src/utils/entry-mode.js'

function handler(page, name, context) {
  const { descriptor } = parse(readFileSync(`src/views/${page}/index.vue`, 'utf8'))
  const source = descriptor.scriptSetup.content
  const node = babelParse(source, { sourceType: 'module' }).program.body.find(item => item.type === 'FunctionDeclaration' && item.id.name === name)
  return vm.runInNewContext(`(${source.slice(node.start, node.end)})`, context)
}
const ref = value => ({ value })
const nodeId = 'isolated-A', peerNodeId = 'isolated-B'
const expiresAt = new Date(Date.now() + 3600000).toISOString()
const payload = crypto.getRandomValues(new Uint8Array(16)), keyHash = await keyHashOf(payload)
const values = { nodeId, peerNodeId, poolId: 'isolated-unit-pool', keyHash, expiresAt }
// Upgrade an existing v5 database without replacing its protector or session K.
const oldProtector = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
const oldIv = crypto.getRandomValues(new Uint8Array(12))
const oldSealed = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: oldIv }, oldProtector, payload)
const oldDb = await new Promise((resolve, reject) => {
  const req = indexedDB.open(KEYSTORE_DB_NAME, 5)
  req.onupgradeneeded = () => {
    for (const [name, keyPath] of [['meta','k'],['keys','keyRef'],['deviceKeys','keyRef'],['sessionKeys','sessionId'],['agreementStates','id']]) req.result.createObjectStore(name, { keyPath })
  }
  req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error)
})
await new Promise((resolve, reject) => {
  const tx = oldDb.transaction(['meta', 'sessionKeys', 'keys'], 'readwrite')
  tx.objectStore('meta').add({ k: 'protector', key: oldProtector })
  tx.objectStore('sessionKeys').add({ sessionId: 'preserved-v5-session', iv: oldIv, sealed: oldSealed })
  tx.objectStore('keys').add({ keyRef: 'node/existing/SM2/existing-key/1', iv: oldIv, sealed: oldSealed, publicKey: 'existing-public' })
  tx.oncomplete = resolve; tx.onerror = () => reject(tx.error)
})
oldDb.close()
await store.sealPoolSecret(values, payload)
assert.deepEqual(await store.unsealSessionSecret('preserved-v5-session'), payload)
await assert.rejects(store.nextLocalPoolSecret(nodeId, peerNodeId), /没有可取用/)
await store.markPoolSecretsUploaded(nodeId, values.poolId, [keyHash])
assert.deepEqual(await store.nextLocalPoolSecret(nodeId, peerNodeId), { poolId: values.poolId, keyHash })
await assert.rejects(store.nextLocalPoolSecret('other-node', peerNodeId), /没有可取用/)
await assert.rejects(store.bindPoolSecretToSession({ ...values, peerNodeId: 'other-peer' }, 'session'), /缺少/)
await assert.rejects(store.bindPoolSecretToSession({ ...values, keyHash: '0'.repeat(64) }, 'session'), /缺少/)
await assert.rejects(store.sealPoolSecret({ ...values, poolId: 'bad-hash', keyHash: '0'.repeat(64) }, payload), /摘要/)
assert.deepEqual(payload.length, 16)
await store.bindPoolSecretToSession(values, 'isolated-unit-session')
assert.deepEqual(await store.unsealSessionSecret('isolated-unit-session'), payload)
await store.bindPoolSecretToSession(values, 'isolated-unit-session') // idempotent retry
await assert.rejects(store.bindPoolSecretToSession(values, 'other-session'), /其他会话/)
await assert.rejects(store.nextLocalPoolSecret(nodeId, peerNodeId), /没有可取用/)
await store.sealPoolSecret({ ...values, poolId: 'expired', expiresAt: '2000-01-01' }, payload)
await assert.rejects(store.nextLocalPoolSecret(nodeId, peerNodeId), /没有可取用/)

const warning = [], errors = []
const messages = { success() {}, info() {}, warning: text => warning.push(text), error: text => errors.push(text) }
const apiItems = new Map(), receiverKeys = new Map()
let uploads = 0, consumes = 0, failLocalSave = false
const context = {
  ...store, technicalFlow: ref(null), ElMessage: messages, Uint8Array, crypto, performance,
  submitting: ref(false), result: ref(null), errorMessage: ref(''), selfNodeId: ref(nodeId),
  form: { nodeCode: peerNodeId, receiverNodeCode: peerNodeId, count: 2, ttlHours: 1 },
  falconKey: ref({ keyId: 'isolated-sign', keyVersion: 1, keyRef: 'sign' }), cryptoProvider: {},
  canSubmit: ref(true), poolAvailable: ref(true), chunkSize: 200,
  PROTECTION_LABELS: { KYBER: 'Kyber' }, toHex: bytes => Buffer.from(bytes).toString('hex'), newBatchId: () => 'isolated-delivery',
  fetchPeerKyberKey: async () => ({ keyId: 'recipient', keyVersion: 1, publicKey: 'public' }),
  generatePayloadKey: () => crypto.getRandomValues(new Uint8Array(16)),
  buildNodeEnvelope: async ({ payloadKey }) => {
    const hash = await keyHashOf(payloadKey)
    receiverKeys.set(hash, payloadKey.slice()) // represents B's correctly unwrapped payload
    return { envelope: { key_hash: hash }, keyHash: hash }
  },
  sealPoolSecret: async (...args) => {
    if (failLocalSave) throw Error('isolated local save failure')
    await store.sealPoolSecret(...args)
  },
  signNodeEnvelope: async () => 'signature',
  preallocatePool: async ({ poolId, items }) => {
    uploads++
    for (const item of items) {
      assert(!('payloadKey' in item)); assert(!('keyHex' in item))
      apiItems.set(item.keyHash, { ...item, poolId })
    }
    return { generated: items.length, failed: [] }
  },
  consumePoolItem: async ({ poolId, keyHash: hash }) => {
    consumes++
    const item = apiItems.get(hash)
    assert(item); assert.equal(poolId, item.poolId)
    apiItems.delete(hash)
    // Exact production contract: no keyHex, no plaintext K.
    return { poolId, keyHash: hash, sessionId: 'isolated-flow-' + consumes, recipientKeyId: 'recipient',
      recipientKeyVersion: 1, envelopeId: consumes, envelope: item.envelope, remaining: apiItems.size }
  },
  signPoolEnvelope: async () => ({}), loadBatches: async () => {}, loadPoolSummary: async () => {}, describeError: error => error.message
}
await handler('preallocate', 'submit', context)()
assert.equal(context.result.value.generated, 2)
assert.equal(uploads, 1)
const generatedSecrets = [...receiverKeys.values()]
// The copied receiver materials are the only plaintext retained in this test.
await handler('distribute', 'handleDistributeFromPool', context)()
assert.equal(context.result.value.keyStored, true)
assert.equal(errors.length, 0, errors.join(';'))
const sessionId = context.result.value.sessionId
const senderSecret = await store.unsealSessionSecret(sessionId)
const receiverSecret = receiverKeys.get(context.result.value.localKeyHash)
assert.deepEqual(senderSecret, receiverSecret)
const proof = await sessionProofFromStore(sessionId)
const hmac = await crypto.subtle.importKey('raw', receiverSecret, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
const receiverProof = Buffer.from(await crypto.subtle.sign('HMAC', hmac, new TextEncoder().encode(sessionId))).toString('hex')
assert.equal(proof, receiverProof, 'A and B must confirm the original, identical SM4')

// The actual session page shows A's button using the persisted session summary.
const sessionContext = { localKeySessions: ref(new Set((await store.listSessionSecrets()).map(item => item.sessionId))), TERMINAL: ['closed', 'expired', 'revoked'] }
const canConfirm = handler('selfSessions', 'canConfirm', sessionContext)
assert(canConfirm({ sessionId, status: 'key_recovered', confirmedCount: 1 }))
assert(!canConfirm({ sessionId, status: 'established', confirmedCount: 2 }))
assert(!canConfirm({ sessionId: 'old-lost-session', status: 'key_recovered' }))

// Stop before consuming server resources if no corresponding local secret exists.
context.selfNodeId.value = 'missing-local-node'
await handler('distribute', 'handleDistributeFromPool', context)()
assert.equal(consumes, 1)
assert.match(context.errorMessage.value, /本机没有可取用/)
context.selfNodeId.value = nodeId
failLocalSave = true
await handler('preallocate', 'submit', context)()
assert.equal(uploads, 1, 'never upload a package whose sender material could not be saved')

// A rejected item must not become the next locally selectable pool resource.
failLocalSave = false
context.selfNodeId.value = 'isolated-partial-A'
let rejectedHash
context.preallocatePool = async ({ items }) => {
  rejectedHash = items[0].keyHash
  return { generated: 1, failed: [{ index: 0, message: 'isolated rejection' }] }
}
await handler('preallocate', 'submit', context)()
const acceptedLocal = await store.nextLocalPoolSecret('isolated-partial-A', peerNodeId)
assert.notEqual(acceptedLocal.keyHash, rejectedHash)

// Inspect the actual storage representation: authenticated encryption, no raw K.
const db = await new Promise((resolve, reject) => {
  const req = indexedDB.open(KEYSTORE_DB_NAME); req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error)
})
const records = await new Promise((resolve, reject) => {
  const req = db.transaction('poolKeys').objectStore('poolKeys').getAll()
  req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error)
})
assert(records.length >= 4)
for (const record of records) {
  assert(record.iv && record.sealed)
  assert(!('payloadKey' in record)); assert(!('keyHex' in record))
  assert(!generatedSecrets.some(bytes => Buffer.from(record.sealed).equals(Buffer.from(bytes))))
}
const preserved = await new Promise(resolve => {
  const req = db.transaction('keys').objectStore('keys').get('node/existing/SM2/existing-key/1')
  req.onsuccess = () => resolve(req.result)
})
assert.equal(preserved.publicKey, 'existing-public')
assert.deepEqual(preserved.sealed, oldSealed, 'v6 upgrade must preserve existing long-term key records byte for byte')
db.close()
console.log('PASS: actual preallocate → sealed pool K → targeted consume (no keyHex) → session persistence → A/B matching HMAC and A confirmation button')
console.log('PASS: node/peer/hash isolation, idempotency, no replacement, expiry, missing-local preflight, save failure blocks upload and encrypted-at-rest records')
console.log('PASS: v5→v6 upgrade retains old protector/keys/sessions and partial upload selects only accepted items')
