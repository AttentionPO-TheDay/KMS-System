import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { falconRecipientState, protectionLabel } from '../src/utils/protection-algorithms.js'
const source = readFileSync(new URL('../src/utils/node-initialization.js', import.meta.url), 'utf8')
const selection = source.slice(source.indexOf('export const INITIALIZATION_ALGORITHMS'), source.indexOf('const metadataKey'))
  .replaceAll('export ', '')
const algorithms = vm.runInNewContext(`${selection}; initializationAlgorithms`)
assert.equal(algorithms({ status: 'PENDING_INIT', falconClCapability: { enabled: true } }).length, 5)
assert.equal(algorithms({ status: 'PENDING_INIT', falconClCapability: { enabled: false } }).length, 4)
assert.equal(algorithms({ status: 'ACTIVE', falconClCapability: { enabled: true } }).length, 4)
const input = { enabled: true, receiverNodeCode: 'receiver', keys: [] }
assert.equal(falconRecipientState(input).available, false)
assert(falconRecipientState(input).message.includes('receiver'))
const key = { algorithm: 'FALCON_CL_V1', purpose: 'ENCRYPT', materialVersion: 1, allowsNewWork: true, publicKey: 'public' }
assert(falconRecipientState({ ...input, keys: [key] }).available)
assert(!falconRecipientState({ ...input, keys: [{ ...key, allowsNewWork: false }] }).available)
assert(!falconRecipientState({ ...input, keys: [{ ...key, purpose: 'SIGN' }] }).available)
assert.equal(protectionLabel('kyber_kem'), protectionLabel('KYBER'))
assert.equal(protectionLabel('falcon_cl_v1'), protectionLabel('FALCON_CL_V1'))
const distribution = readFileSync(new URL('../src/views/distribute/index.vue', import.meta.url), 'utf8')
assert(!distribution.includes(':disabled="!falconClReady"'))
assert(!distribution.includes('ownFalconClReady'))
console.log('PASS: 首次五套/功能关闭四套/旧 ACTIVE 兼容、接收方密钥与分发选择、算法名称')
