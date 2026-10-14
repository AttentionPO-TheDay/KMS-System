import assert from 'node:assert/strict'
import { createAutoUpdateRunner } from '../src/utils/node-auto-update-runner.js'

let identity = 'node-1'
let loggedIn = true
let policies = []
let claims = 0
let rotations = []
let completions = []
let changed = 0
let rotateError = ''
const deps = {
  isLoggedIn: () => loggedIn, identity: () => identity,
  getPolicies: async () => ({ nodeId: 'node-1', serverTime: '2026-10-13T12:00:00', policies }),
  claim: async algorithm => {
    claims++
    return { claim: { algorithm, keyId: 'key-1', fromVersion: 3, leaseToken: 'lease-1' } }
  },
  rotate: async options => {
    rotations.push(options)
    assert.equal(await options.confirmUnusedIssuance(), false)
    if (rotateError) throw new Error(rotateError)
  },
  complete: async (...args) => { completions.push(args); return { lastResult: rotateError ? 'FAILED' : 'SUCCESS' } },
  changed: () => changed++
}
const runner = createAutoUpdateRunner(deps)
policies = [{ algorithm: 'SM2', enabled: false, nextRunAt: '2026-10-13T11:00:00' },
  { algorithm: 'SSCL', enabled: true, nextRunAt: '2026-10-13T13:00:00' }]
await runner.tick()
assert.equal(claims, 0)
policies = [{ algorithm: 'SM2', enabled: true, nextRunAt: '2026-10-13T11:00:00' }]
await runner.tick()
assert.equal(rotations.length, 1)
assert.equal(rotations[0].keyId, 'key-1')
assert.equal(rotations[0].version, 4)
assert.equal(rotations[0].rotate, true)
assert.deepEqual(completions[0], ['SM2', 'lease-1', ''])
assert.equal(changed, 1)
rotateError = '本机材料未通过对账'
await runner.tick()
assert.equal(completions[1][2], rotateError)
loggedIn = false
await runner.tick()
assert.equal(rotations.length, 2)
loggedIn = true
deps.claim = async () => ({ claim: null })
await runner.tick()
assert.equal(rotations.length, 2)
deps.getPolicies = async () => { identity = 'node-2'; return { policies } }
await runner.tick()
assert.equal(rotations.length, 2)

let release
let runs = 0
const blocking = createAutoUpdateRunner({ ...deps,
  getPolicies: () => { runs++; return new Promise(resolve => { release = resolve }) } })
const pending = blocking.tick()
await blocking.tick()
assert.equal(runs, 1)
release({ policies: [] })
await pending
console.log('PASS: 到期触发、版本递增、关闭、不重复执行、失败反馈、身份切换和并发锁')

// Exercise the production rotation workflow with real encrypted local SM2 material.
// Only the remote registry is in memory; no production API or business key is touched.
await import('fake-indexeddb/auto')
const { readFileSync } = await import('node:fs')
const vm = await import('node:vm')
const { cryptoProvider } = await import('../src/utils/crypto/browser-provider.js')
const store = await import('../src/utils/crypto/node-key-store.js')
const compare = await import('../src/utils/crypto/node-key-compare.js')
const keyRef = await import('../src/utils/crypto/key-ref.js')
const generation = await import('../src/utils/crypto/generation-scheme.js')
const source = readFileSync(new URL('../src/utils/node-initialization.js', import.meta.url), 'utf8')
const workflowSource = source.slice(source.indexOf('const metadataKey'), source.indexOf('\nconst service ='))
  .replace('export function createNodeInitializationService', 'function createNodeInitializationService')
const factory = vm.runInNewContext(`${workflowSource}; createNodeInitializationService`, {
  ...compare, ...keyRef, ...generation, NODE_SELF_ERR: {}, AbortController, setInterval, clearInterval
})
const nodeId = 'isolated-auto-node'
const demo = { principalType: 'NODE', nodeId }
const first = await cryptoProvider.generate('SM2', { nodeId, version: 1 })
let registry = [{ ...first, keyVersion: 1, status: 'ACTIVE', allowsNewWork: true, allowsUnwrap: true }]
let keygens = 0
let registrations = 0
let rejectSelfTest = true
const workflow = factory({
  ...store, isDemo: true, entryMode: 'DEMO', getDemoContext: () => demo,
  getSelfNode: async () => ({ mapped: true, node: { nodeId, status: 'ACTIVE' } }),
  listSelfNodeKeys: async () => ({ nodeId, keys: registry }),
  locks: { request: async (_name, _options, operation) => operation({ name: 'isolated' }) },
  generate: async (...args) => { keygens++; return cryptoProvider.generate(...args) },
  selfTest: async (...args) => rejectSelfTest ? { ok: false, detail: 'isolated failure' } : cryptoProvider.selfTest(...args),
  registerSelfNodePublicKey: async (algorithm, publicKey, _security, _device, keyId, version, rotate) => {
    assert.equal(rotate, true)
    assert.equal(keyId, first.keyId)
    assert.equal(version, 2)
    assert.notEqual(publicKey, first.publicKey)
    registrations++
    registry[0] = { ...registry[0], algorithm, publicKey, keyVersion: version }
    return { keyId, keyVersion: version }
  }
})
let result
let due = true
const realRunner = createAutoUpdateRunner({
  isLoggedIn: () => true, identity: () => demo,
  getPolicies: async () => ({ nodeId, serverTime: '2026-10-13T12:00:00', policies: [{ algorithm: 'SM2', enabled: due, nextRunAt: '2026-10-13T11:00:00' }] }),
  claim: async () => ({ claim: { algorithm: 'SM2', keyId: first.keyId, fromVersion: 1, leaseToken: 'isolated' } }),
  rotate: workflow.generateAndRegisterNodeKey,
  complete: async (_algo, _token, message) => {
    result = registry[0].keyVersion === 2 ? 'SUCCESS' : 'FAILED'
    if (result === 'SUCCESS') due = false
    else assert(message.includes('自检未过'))
    return { lastResult: result }
  }, changed() {}
})
await realRunner.tick()
assert.equal(result, 'FAILED')
assert.equal(registrations, 0)
assert.equal(registry[0].keyVersion, 1)
rejectSelfTest = false
await realRunner.tick()
assert.equal(result, 'SUCCESS')
assert.equal(keygens, 1, 'retry reuses sealed v2 instead of generating again')
assert.equal(registrations, 1)
await realRunner.tick()
assert.equal(registrations, 1)
const materials = await store.inspectNodeKeys(nodeId)
assert.equal(materials.keys.length, 2)
const updated = materials.keys.find(row => row.version === 2)
assert((await cryptoProvider.selfTest('SM2', updated.keyRef)).ok)
assert.equal(updated.keyId, first.keyId)
console.log('PASS: 实际 SM2 自动换版、加密封存、自检、失败保留旧版本、重试复用材料')
