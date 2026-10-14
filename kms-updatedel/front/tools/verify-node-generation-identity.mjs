// Isolated encrypted SM2 keys and in-memory registry, no production APIs.
import assert from 'node:assert/strict'
import 'fake-indexeddb/auto'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { cryptoProvider } from '../src/utils/crypto/browser-provider.js'
import * as store from '../src/utils/crypto/node-key-store.js'
import * as compare from '../src/utils/crypto/node-key-compare.js'
import * as keyRef from '../src/utils/crypto/key-ref.js'
import * as generation from '../src/utils/crypto/generation-scheme.js'

const source = readFileSync(new URL('../src/utils/node-initialization.js', import.meta.url), 'utf8')
const factory = vm.runInNewContext(`${source.slice(source.indexOf('const metadataKey'), source.indexOf('\nconst service ='))
  .replace('export function createNodeInitializationService', 'function createNodeInitializationService')}; createNodeInitializationService`,
{ ...compare, ...keyRef, ...generation, NODE_SELF_ERR: {}, AbortController, setInterval, clearInterval })
const nodeId = 'isolated-generation-identity'
const demo = { principalType: 'NODE', nodeId }
const registry = []
let generations = 0, failRegister = false, failSelfTest = false
const workflow = factory({
  ...store, isDemo: true, entryMode: 'DEMO', getDemoContext: () => demo,
  getSelfNode: async () => ({ mapped: true, node: { nodeId, status: 'ACTIVE' } }),
  listSelfNodeKeys: async options => {
    assert.equal(options.includeRegistry, true)
    // History is deliberately omitted from the displayed list.
    return { nodeId, keys: registry.filter(key => key.status === 'ACTIVE'),
      keyIdentities: registry.map(({ algorithm, keyId, keyVersion }) => ({ algorithm, keyId, keyVersion })) }
  },
  locks: { request: async (_name, _options, operation) => operation({}) },
  generate: async (...args) => { generations++; return cryptoProvider.generate(...args) },
  selfTest: async (...args) => failSelfTest ? { ok: false, detail: 'isolated self-test failure' } : cryptoProvider.selfTest(...args),
  registerSelfNodePublicKey: async (algorithm, publicKey, _security, _device, keyId, version, rotate) => {
    if (failRegister) throw new Error('isolated registry failure')
    const existing = registry.find(key => key.keyId === keyId)
    if (rotate) { assert(existing); assert.equal(version, existing.keyVersion + 1) }
    else { assert(!existing); assert.equal(version, 1) }
    registry.forEach(key => { key.status = 'RETIRED'; key.allowsNewWork = false })
    registry.push({ algorithm, keyId, keyVersion: version, publicKey, status: 'ACTIVE', allowsNewWork: true, allowsUnwrap: true })
    return { keyId, keyVersion: version }
  }
})
const generate = options => workflow.generateAndRegisterNodeKey({ algorithm: 'SM2', nodeId, ...options })
const first = await generate()
const second = await generate()
assert.notEqual(first.material.keyId, second.material.keyId)
assert.notEqual(first.material.publicKey, second.material.publicKey)
assert.equal(generations, 2, 'registered historical material must never be recovered as new generation')
const updated = await generate({ rotate: true, keyId: second.material.keyId, version: 2 })
assert.equal(updated.material.keyId, second.material.keyId)
assert.equal(updated.material.version, 2)
assert.equal(new Set(registry.map(key => key.keyId)).size, 2)
await assert.rejects(generate({ keyId: first.material.keyId }), /新的 keyId/)
await assert.rejects(generate({ version: 2 }), /版本从 1/)
failSelfTest = true
await assert.rejects(generate(), /自检未过/)
const count = generations
failSelfTest = false; failRegister = true
await assert.rejects(generate(), /isolated registry failure/)
assert.equal(generations, count)
failRegister = false
const recovered = await generate()
assert.equal(recovered.reused, true)
assert.equal(generations, count)
assert.equal(new Set(registry.map(key => key.keyId)).size, 3)
console.log('PASS: 连续生成新 ID/v1、更新原 ID/v2、完整历史索引、拒绝生成旧 ID、失败重试复用封存材料')
