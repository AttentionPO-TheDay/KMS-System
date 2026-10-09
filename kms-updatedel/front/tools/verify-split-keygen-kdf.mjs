// Isolated Node/WebCrypto + fake IndexedDB: never touches a browser's real keys or a server.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import 'fake-indexeddb/auto'
import { deriveSplitSeed, encodeGenerationContext, issueSplitSeed } from '../src/utils/crypto/split-keygen.js'
import { publicGeneration, publicGenerationContext, formatGenerationName, GENERATION_CONTEXT_FIELDS } from '../src/utils/crypto/generation-scheme.js'
import { normalizeAlgorithm } from '../src/utils/crypto/provider.js'
import { BrowserCryptoProvider } from '../src/utils/crypto/browser-provider.js'
import { requireLocalKey, unsealSecret, listSecrets, listMetaRecords, sealSecret, updateGenerationAuthorization, DB_NAME } from '../src/utils/crypto/node-key-store.js'

const fixture = JSON.parse(readFileSync(new URL('./fixtures/split-keygen-v1.json', import.meta.url), 'utf8'))
const hex = bytes => Buffer.from(bytes).toString('hex')
const share = Uint8Array.from(Buffer.from(fixture.kgcShareHex, 'hex'))
const localSecret = Uint8Array.from(Buffer.from(fixture.localSecretHex, 'hex'))
let checks = 0
function check() { checks++ }
for (const vector of fixture.vectors) {
  assert.equal(hex(await deriveSplitSeed(share, localSecret, vector.context)), vector.seedHex); check()
  assert.equal(hex(await deriveSplitSeed(share, localSecret, vector.context)), vector.seedHex); check()
  assert.equal(encodeGenerationContext(vector.context).subarray(0, 25).length, 25)
  const changedShare = share.slice(); changedShare[0] ^= 1
  const changedLocal = localSecret.slice(); changedLocal[0] ^= 1
  assert.notEqual(hex(await deriveSplitSeed(changedShare, localSecret, vector.context)), vector.seedHex); check()
  assert.notEqual(hex(await deriveSplitSeed(share, changedLocal, vector.context)), vector.seedHex); check()
  assert.equal(hex(share), fixture.kgcShareHex)
  assert.equal(hex(localSecret), fixture.localSecretHex)
  for (const [field, value] of Object.entries({ userId: '8', nodeId: '节点-β', keyId: 'other-key', keyVersion: '3', generationIssuanceId: 'other-issuance' })) {
    assert.notEqual(hex(await deriveSplitSeed(share, localSecret, { ...vector.context, [field]: value })), vector.seedHex); check()
  }
}
const kem = fixture.vectors[0]
for (const change of [{ deviceFingerprint: 'other-device' }, { variant: '512' }, { variant: '1024' }, { bindingKind: 'DEMO', deviceFingerprint: '', demoSessionId: 'demo-session', demoRevision: '1' }]) {
  assert.notEqual(hex(await deriveSplitSeed(share, localSecret, { ...kem.context, ...change })), kem.seedHex); check()
}
const sign = fixture.vectors[1]
for (const change of [{ demoSessionId: 'other-session' }, { demoRevision: '4' }]) {
  assert.notEqual(hex(await deriveSplitSeed(share, localSecret, { ...sign.context, ...change })), sign.seedHex); check()
}
for (const field of GENERATION_CONTEXT_FIELDS) {
  const incomplete = { ...kem.context }; delete incomplete[field]
  assert.throws(() => publicGenerationContext(incomplete)); check()
}
for (const change of [{ schemeId: 'KMS_SPLIT_KEM_V2' }, { schemeVersion: '2' }, { purpose: 'SIGN_KEYGEN' }, { coreFamily: 'FALCON' }, { keyVersion: '02' }, { userId: ' 7' }, { demoRevision: '0' }, { secret: 'DO_NOT_STORE' }]) {
  assert.throws(() => publicGenerationContext({ ...kem.context, ...change })); check()
}
assert.throws(() => publicGeneration({ schemeId: 'KMS_SPLIT_KEM_V1', schemeVersion: 1, generationIssuanceId: 'i', authorizationTicketId: 'a', seed: 'DO_NOT_STORE' })); check()
assert.equal(normalizeAlgorithm('kyber_kem'), 'KYBER')
assert.equal(normalizeAlgorithm('CL-Falcon'), 'FALCON')
assert.equal(normalizeAlgorithm('KMS_NEW_KYBER'), 'KMS_NEW_KYBER')
assert.equal(normalizeAlgorithm('ML-KEM'), 'ML-KEM')
assert.equal(normalizeAlgorithm('KMS_SPLIT_KEM_V1'), 'KMS_SPLIT_KEM_V1')
assert.match(formatGenerationName('KYBER'), /来源未记录/)
assert.match(formatGenerationName('KYBER', 'KMS_SPLIT_KEM_V1'), /实验版/)
assert.throws(() => formatGenerationName('KYBER', 'KMS_NEW_KYBER')); check()

const request = { algorithm: 'KYBER', nodeId: 'KDF-NODE', keyId: 'key-kem', keyVersion: 1, variant: 768 }
const expectedIdentity = { nodeId: request.nodeId, userId: '7', bindingKind: 'DEVICE', deviceFingerprint: kem.context.deviceFingerprint, demoSessionId: '', demoRevision: '' }
function response(req, changes = {}) {
  const signing = req.algorithm === 'FALCON'
  const schemeId = signing ? 'KMS_SPLIT_SIGN_V1' : 'KMS_SPLIT_KEM_V1'
  return {
    generationScheme: schemeId, generationIssuanceId: `issuance-${req.keyId}`, authorizationTicketId: `ticket-${req.keyId}`,
    context: { ...kem.context, schemeId, coreFamily: req.algorithm, purpose: signing ? 'SIGN_KEYGEN' : 'KEM_KEYGEN', variant: String(req.variant), nodeId: req.nodeId, keyId: req.keyId, keyVersion: String(req.keyVersion), generationIssuanceId: `issuance-${req.keyId}` },
    share: Buffer.from(share).toString('base64'), expiresAt: new Date(Date.now() + 60000).toISOString(), ...changes
  }
}
await assert.rejects(() => issueSplitSeed(request), /禁止/); check()
for (const field of Object.keys(expectedIdentity)) {
  const incomplete = { ...expectedIdentity }; delete incomplete[field]
  let called = false
  await assert.rejects(() => issueSplitSeed(request, async req => { called = true; return response(req) }, incomplete), /完整/)
  assert.equal(called, false, 'missing trusted identity rejected before issuance'); check()
}
for (const change of [{ generationScheme: 'OTHER' }, { generationIssuanceId: 'mismatch' }, { share: 'AA==' }, { expiresAt: new Date(0).toISOString() }, { expiresAt: '2099-01-01T00:00:00' }]) {
  await assert.rejects(() => issueSplitSeed(request, async req => response(req, change), expectedIdentity)); check()
}
for (const [field, value] of Object.entries({ nodeId: 'other-node', keyId: 'other-key', keyVersion: '2', variant: '512', purpose: 'SIGN_KEYGEN', userId: '8', deviceFingerprint: 'other-device' })) {
  await assert.rejects(() => issueSplitSeed(request, async req => { const res = response(req); res.context[field] = value; return res }, expectedIdentity)); check()
}
const issuanceResponse = response(request)
const derived = await issueSplitSeed(request, async () => issuanceResponse, expectedIdentity)
assert.equal(derived.seed.length, 64)
assert.equal(issuanceResponse.share, undefined)
assert.equal(Object.hasOwn(derived, 'share'), false)
derived.seed.fill(0); check()
const otherLocal = await issueSplitSeed(request, async req => response(req), expectedIdentity)
assert.notEqual(hex(otherLocal.seed), '0'.repeat(128)); otherLocal.seed.fill(0)
const demoIdentity = { nodeId: request.nodeId, userId: '7', bindingKind: 'DEMO', deviceFingerprint: '', demoSessionId: 'server-hashed-session', demoRevision: '3' }
const demoIssuer = async req => { const res = response(req); Object.assign(res.context, demoIdentity); return res }
const demo = await issueSplitSeed(request, demoIssuer, demoIdentity)
assert.equal(demo.seed.length, 64); demo.seed.fill(0); check()
await assert.rejects(() => issueSplitSeed(request, demoIssuer, { ...demoIdentity, demoSessionId: 'other-session' }), /可信身份/); check()
await assert.rejects(() => issueSplitSeed(request, demoIssuer, { ...demoIdentity, demoRevision: '4' }), /可信身份/); check()

const provider = new BrowserCryptoProvider()
let issued = 0
const issuer = async req => { issued++; return response(req) }
await assert.rejects(() => provider.generate('KYBER', { nodeId: request.nodeId, keyId: 'no-issuer' }), /禁止/); check()
for (const algorithm of ['KYBER', 'FALCON']) {
  const keyId = `provider-${algorithm}`
  const generated = await provider.generate(algorithm, { nodeId: request.nodeId, keyId, variant: algorithm === 'KYBER' ? 768 : 512, issueKeygen: issuer, generationContext: expectedIdentity })
  assert.deepEqual(Object.keys(generated.generation).sort(), ['schemeId', 'schemeVersion', 'generationIssuanceId', 'authorizationTicketId'].sort())
  const summary = await requireLocalKey(generated.keyRef)
  assert.deepEqual(summary.generation, generated.generation)
  assert.deepEqual(summary.generationContext, generated.generationContext)
  const before = hex(await unsealSecret(generated.keyRef))
  const calls = issued
  await assert.rejects(() => provider.generate(algorithm, { nodeId: request.nodeId, keyId, issueKeygen: issuer }), /封存/)
  assert.equal(issued, calls, 'existing-key guard before issuance')
  assert.equal(hex(await unsealSecret(generated.keyRef)), before)
  assert.equal((await provider.selfTest(algorithm, generated.keyRef)).ok, true)
  const renewed = await updateGenerationAuthorization(generated.keyRef, 'ticket-renewed')
  assert.equal(renewed.generation.authorizationTicketId, 'ticket-renewed')
  assert.equal(renewed.generation.generationIssuanceId, generated.generation.generationIssuanceId)
  assert.deepEqual(renewed.generationContext, generated.generationContext)
  assert.equal(hex(await unsealSecret(generated.keyRef)), before)
  assert.equal((await provider.selfTest(algorithm, generated.keyRef)).ok, true)
  check()
}
assert.equal(issued, 2)
assert.equal((await listSecrets()).length, 2)
const binaryRequest = { ...request, keyId: 'binary-import' }
const binaryResponse = response(binaryRequest)
const binaryGeneration = { schemeId: binaryResponse.generationScheme, schemeVersion: 1, generationIssuanceId: binaryResponse.generationIssuanceId, authorizationTicketId: binaryResponse.authorizationTicketId }
const binaryRef = 'node/KDF-NODE/KYBER/binary-import/1'
const binarySecret = Uint8Array.from([0, 255, 128, 192, 175, 254, 1, 127])
await provider.importSecret(binaryRef, { algorithm: 'KYBER', secret: binarySecret, publicKey: 'fixed-public', generation: binaryGeneration, generationContext: binaryResponse.context })
assert.deepEqual(await unsealSecret(binaryRef), binarySecret, 'split provenance preserves binary imports losslessly')
await updateGenerationAuthorization(binaryRef, 'binary-renewed')
assert.deepEqual(await unsealSecret(binaryRef), binarySecret, 'renewal preserves binary imports losslessly'); check()
const meta = await listMetaRecords()
assert.ok(meta.every(record => !Object.keys(record).some(key => /share|seed|localSecret|kgc/i.test(key))), 'no contribution/public-meta leakage')
await sealSecret('node/KDF-NODE/SM2/historical/1', { secret: 'historical-private', publicKey: 'historical-public' })
assert.equal(new TextDecoder().decode(await unsealSecret('node/KDF-NODE/SM2/historical/1')), 'historical-private')
await assert.rejects(() => updateGenerationAuthorization('node/KDF-NODE/SM2/historical/1', 'fake-ticket'), /历史/); check()

// Outer metadata tampering must fail rather than acquire a new scheme label/recovery source.
const db = await new Promise((resolve, reject) => { const req = indexedDB.open(DB_NAME); req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error) })
const ref = 'node/KDF-NODE/KYBER/provider-KYBER/1'
await new Promise((resolve, reject) => {
  const tx = db.transaction('keys', 'readwrite'); const store = tx.objectStore('keys'); const get = store.get(ref)
  get.onsuccess = () => { const record = get.result; record.generation.authorizationTicketId = 'tampered-ticket'; store.put(record) }
  tx.oncomplete = resolve; tx.onerror = () => reject(tx.error)
})
await assert.rejects(() => requireLocalKey(ref), /改动/)
await assert.rejects(() => listSecrets(), /改动/)
db.close(); check()
console.info(`Split KeyGen HKDF/provider PASS: ${checks} assertion groups; frozen JS/Python vectors; context/issuer validation; no fallback/overwrite; sealed-first provenance and authorization renewal; tamper rejection; historical secret decoding`)
