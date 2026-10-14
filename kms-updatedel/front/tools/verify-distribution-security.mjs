#!/usr/bin/env node
import assert from 'node:assert/strict'
import { sm4GcmEncrypt, sm4GcmDecrypt } from '../src/utils/sm4.js'
import { unwrapNodeEnvelope, checkRecoveredKeyHash } from '../src/utils/crypto/node-envelope.js'
import { createDistributionFixtures, mutateBase64 } from './distribution-security-fixtures.mjs'

let checks = 0
function check(name, run) {
  run(); checks++; console.log(`[PASS] ${name}`)
}
const key = crypto.getRandomValues(new Uint8Array(16))
const iv = crypto.getRandomValues(new Uint8Array(12))
const plaintext = crypto.getRandomValues(new Uint8Array(16))
const { ciphertext, tag } = sm4GcmEncrypt(key, plaintext, iv)
check('valid SM4-GCM envelope still decrypts', () => assert.deepEqual(sm4GcmDecrypt(key, ciphertext, iv, tag), plaintext))
for (const invalid of [undefined, null, [], new Uint8Array(0), tag.slice(0, 15), Uint8Array.from([...tag, 0])]) {
  check('missing/non-byte/truncated/overlong tag rejects', () => assert.throws(() => sm4GcmDecrypt(key, ciphertext, iv, invalid), /SM4-GCM 认证失败/))
}
for (let i = 0; i < 16; i++) {
  const bad = Uint8Array.from(tag); bad[i] ^= 1
  check(`tag tamper byte ${i} rejects`, () => assert.throws(() => sm4GcmDecrypt(key, ciphertext, iv, bad), /SM4-GCM 认证失败/))
}
const fixtures = await createDistributionFixtures({ includeFalcon: true })
try {
  const { provider, payloadKey, kyber, sm2, sscl } = fixtures
  for (const [algorithm, ref, envelope] of [['KYBER', 'TEST_ONLY_KYBER', kyber], ['SM2', 'TEST_ONLY_SM2', sm2], ['SSCL', 'TEST_ONLY_SM2', sscl]]) {
    const recovered = await unwrapNodeEnvelope({ provider, keyRef: ref, envelope })
    check(`${algorithm} real provider envelope roundtrip`, () => assert.deepEqual(recovered, payloadKey))
    recovered.fill(0)
  }
  const message = new TextEncoder().encode('TEST_ONLY cleanup verification')
  const signed = await provider.sign('FALCON', 'TEST_ONLY_FALCON', message)
  check('Falcon real signature created', () => assert.ok(signed.length > message.length))
  const failures = [
    { ...kyber, tag: mutateBase64(kyber.tag) },
    { ...kyber, tag: mutateBase64(kyber.tag, -1) },
    { ...kyber, tag: '' },
    { ...kyber, tag: Buffer.concat([Buffer.from(kyber.tag, 'base64'), Buffer.from([0])]).toString('base64') },
    { ...kyber, encrypted_key: mutateBase64(kyber.encrypted_key) },
    { ...kyber, kem_ciphertext: mutateBase64(kyber.kem_ciphertext) },
    { ...kyber, nonce: '!' },
    { ...sm2, ciphertext: sm2.ciphertext.slice(0, -2) + (sm2.ciphertext.endsWith('00') ? '01' : '00') },
    { ...sscl, ciphertext: '04' },
    { wrapping_algorithm: 'unsupported' }
  ]
  for (const envelope of failures) {
    await assert.rejects(unwrapNodeEnvelope({ provider, keyRef: envelope.wrapping_algorithm === 'kyber_kem' ? 'TEST_ONLY_KYBER' : 'TEST_ONLY_SM2', envelope }), error => {
      assert.equal(error.code, 'NODE_ENVELOPE_UNWRAP_FAILED')
      assert.equal(error.message, '节点信封解封失败：信封完整性校验失败或本机密钥不匹配')
      assert.equal(error.cause, undefined)
      return true
    })
    checks++; console.log('[PASS] tampered envelope returns only uniform failure; no key returned')
  }
  await assert.rejects(provider.unwrapEnvelope('KYBER', 'TEST_ONLY_MISSING', kyber), { code: 'NODE_ENVELOPE_UNWRAP_FAILED' })
  checks++
  provider.secrets.set('TEST_ONLY_INVALID_SIZE', new Uint8Array(32).fill(7))
  await assert.rejects(provider.decapsulate('KYBER', 'TEST_ONLY_INVALID_SIZE', new Uint8Array(1088)))
  checks++; console.log('[PASS] invalid Kyber private key size rejects')
  await assert.rejects(provider.sign('FALCON', 'TEST_ONLY_INVALID_SIZE', message))
  checks++; console.log('[PASS] invalid Falcon private key size rejects')
  for (const length of [0, 15, 17]) {
    const returned = new Uint8Array(length).fill(7)
    await assert.rejects(unwrapNodeEnvelope({ provider: { unwrapEnvelope: async () => returned }, envelope: kyber }), { code: 'NODE_ENVELOPE_UNWRAP_FAILED' })
    check('invalid recovered length rejects and clears buffer', () => assert.ok(returned.every(b => b === 0)))
  }
  const hashFailure = await checkRecoveredKeyHash(payloadKey, { key_hash: '0'.repeat(64) })
  check('key mismatch omits recovered key hash', () => {
    assert.equal(hashFailure.ok, false)
    assert.equal(hashFailure.detail, '节点信封解封失败：信封完整性校验失败或本机密钥不匹配')
    assert.equal(hashFailure.hash, undefined)
  })
  check('temporary private key copies cleared on success and error', () => assert.ok(provider.readBuffers.every(buffer => buffer.every(b => b === 0))))
  check('source private keys and caller payload survive temporary cleanup', () => {
    assert.ok([...provider.secrets.values()].every(buffer => buffer.some(b => b !== 0)))
    assert.ok(payloadKey.some(b => b !== 0))
  })
} finally {
  fixtures.dispose(); key.fill(0); plaintext.fill(0)
}
console.log(`\n${checks} security checks passed. This is functional verification, not constant-time certification.`)
