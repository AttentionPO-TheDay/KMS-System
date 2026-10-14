// TEST ONLY: synthetic matrices and isolated fake IndexedDB; no production API or keys.
import 'fake-indexeddb/auto'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { encodeMaterial, parseMaterial } from '../src/utils/crypto/falcon-cl-v1.js'
import { readEncryptedKeyPackage, publicKeyRecord } from '../src/utils/crypto/encrypted-key-package.js'
import { sealSecret, unsealSecret, updateGenerationAuthorization } from '../src/utils/crypto/node-key-store.js'
import { KEYSTORE_DB_NAME } from '../src/utils/entry-mode.js'

globalThis.fetch = () => { throw new Error('Regression must never upload private material') }
const nodeId = 'TEST_ONLY_LOCAL_PACKAGE'
const keyRef = `node/${nodeId}/FALCON_CL_V1/test/1`
const publicMatrix = new Int32Array(512 * 1024)
const privateMatrix = new Int32Array(1024 * 1024)
const publicKey = encodeMaterial({ A: publicMatrix, B: publicMatrix, H_id: publicMatrix, U_id: publicMatrix }, 'PUBLIC', nodeId)
const secret = encodeMaterial({ D_id: privateMatrix, S_id: privateMatrix }, 'PRIVATE', nodeId)
const generation = { schemeId: 'KMS_SPLIT_FALCON_CL_V1', schemeVersion: 1, generationIssuanceId: 'TEST_ONLY_ISSUANCE', authorizationTicketId: 'TEST_ONLY_TICKET' }
const generationContext = { schemeId: generation.schemeId, schemeVersion: '1', coreFamily: 'FALCON_CL_V1', variant: '512', userId: '0', nodeId,
  bindingKind: 'DEVICE', deviceFingerprint: 'TEST_ONLY_DEVICE', demoSessionId: '', demoRevision: '', keyId: 'test', keyVersion: '1', purpose: 'ENCRYPT', generationIssuanceId: generation.generationIssuanceId }
const summary = await sealSecret(keyRef, { algorithm: 'FALCON_CL_V1', version: 1, publicKey, secret, generation, generationContext, createOnly: true })
assert.equal(summary.publicKey, publicKey)
for (const field of ['iv', 'sealed', 'encryptedKeyPackage', 'secret']) assert.equal(summary[field], undefined)
assert.equal(parseMaterial(publicKey, 'PUBLIC', nodeId).D_id, undefined)
assert.equal(parseMaterial(publicKey, 'PUBLIC', nodeId).S_id, undefined)
assert.throws(() => parseMaterial(secret, 'PUBLIC', nodeId))
console.log('[PASS] Real public material separated from private material and public metadata')

const db = await new Promise((resolve, reject) => {
  const request = indexedDB.open(KEYSTORE_DB_NAME)
  request.onsuccess = () => resolve(request.result)
  request.onerror = () => reject(request.error)
})
const read = () => new Promise((resolve, reject) => {
  const request = db.transaction('keys').objectStore('keys').get(keyRef)
  request.onsuccess = () => resolve(request.result)
  request.onerror = () => reject(request.error)
})
const write = record => new Promise((resolve, reject) => {
  const transaction = db.transaction('keys', 'readwrite')
  transaction.objectStore('keys').put(record)
  transaction.oncomplete = resolve
  transaction.onerror = () => reject(transaction.error)
})
let record = await read()
assert.equal(record.iv, undefined)
assert.equal(record.sealed, undefined)
assert.equal(record.encryptedKeyPackage.cipher, 'AES-256-GCM')
assert.equal(new TextDecoder().decode(await unsealSecret(keyRef)), secret)
assert.equal(publicKeyRecord(record).encryptedKeyPackage, undefined)
console.log('[PASS] Dedicated local ciphertext field and authenticated round-trip')

const broken = structuredClone(record)
new Uint8Array(broken.encryptedKeyPackage.ciphertext)[0] ^= 1
await write(broken)
await assert.rejects(unsealSecret(keyRef), /解密失败/)
await write(record)
assert.throws(() => readEncryptedKeyPackage({ ...record, iv: record.encryptedKeyPackage.iv }), /重复/)
console.log('[PASS] Tampered ciphertext and ambiguous duplicate fields rejected')

// Old records remain usable without regeneration; renewal upgrades the layout.
const old = { ...record, iv: record.encryptedKeyPackage.iv, sealed: record.encryptedKeyPackage.ciphertext }
delete old.encryptedKeyPackage
await write(old)
assert.equal(new TextDecoder().decode(await unsealSecret(keyRef)), secret)
await updateGenerationAuthorization(keyRef, 'TEST_ONLY_RENEWED_TICKET')
record = await read()
assert.equal(record.generation.authorizationTicketId, 'TEST_ONLY_RENEWED_TICKET')
assert.equal(record.iv, undefined)
assert.equal(record.sealed, undefined)
assert.equal(record.publicKey, publicKey)
assert.equal(new TextDecoder().decode(await unsealSecret(keyRef)), secret)
assert.notDeepEqual(record.encryptedKeyPackage.iv, old.iv)
console.log('[PASS] Legacy ciphertext compatible; renewal preserves keys and upgrades layout')

const renewed = await Promise.allSettled([
  updateGenerationAuthorization(keyRef, 'TEST_ONLY_RACE_A'),
  updateGenerationAuthorization(keyRef, 'TEST_ONLY_RACE_B')
])
assert.equal(renewed.filter(result => result.status === 'fulfilled').length, 1)
assert.equal(new TextDecoder().decode(await unsealSecret(keyRef)), secret)
console.log('[PASS] Concurrent renewal rejects stale ciphertext snapshot')

const provider = readFileSync(new URL('../src/utils/crypto/browser-provider.js', import.meta.url), 'utf8')
assert.match(provider, /return \{ publicKey: material\.publicKey, keyRef, keyId, nodeId, version, algorithm: name/)
assert.doesNotMatch(provider, /encryptedKeyPackage/)
console.log('[PASS] Generation DTO does not expose the local ciphertext package; no network used')
db.close()
