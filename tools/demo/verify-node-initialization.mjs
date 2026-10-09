import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import test from 'node:test'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const front = path.join(root, 'kms-updatedel/front/src')
const source = await readFile(path.join(front, 'utils/node-initialization.js'), 'utf8')
// Execute the production dependency-injected core; only browser/alias wiring is excluded.
const core = source.slice(source.indexOf('export const INITIALIZATION_ALGORITHMS'), source.indexOf('\nconst service ='))
const compareURL = pathToFileURL(path.join(front, 'utils/crypto/node-key-compare.js')).href
const moduleURL = `data:text/javascript;base64,${Buffer.from(`import {activeServerKey,findLocalKey,reconcileRow,RECONCILE} from '${compareURL}';\n${core}`).toString('base64')}`
const { createNodeInitializationService, INITIALIZATION_ALGORITHMS } = await import(moduleURL)

function fixture({ demo = true, status = 'PENDING_INIT' } = {}) {
  const node = { nodeId: 'Node-A', status, keys: {} }
  const local = []
  const server = []
  const meta = new Map()
  const calls = { generated: [], registered: [], leased: 0, released: 0, finished: 0, device: 0 }
  const corrupt = new Set()
  let locked = false
  let context = { principalType: 'NODE', nodeId: node.nodeId, revision: 1 }
  const deps = {
    isDemo: demo, entryMode: demo ? 'DEMO' : 'STANDALONE', getDemoContext: () => context,
    getSelfNode: async () => ({ mapped: true, node: { ...node, keys: { ...node.keys } } }),
    listSelfNodeKeys: async () => ({ nodeId: node.nodeId, keys: server.map(row => ({ ...row })) }),
    inspectNodeKeys: async id => ({ keys: local.filter(row => row.nodeId === id).map(row => ({ ...row })) }),
    requireLocalKey: async (ref, expected) => {
      const key = local.find(row => row.keyRef === ref)
      assert(key && key.nodeId === expected.nodeId && key.algorithm === expected.algorithm && key.version === expected.version)
      return { ...key }
    },
    unsealSecret: async ref => {
      if (corrupt.has(ref)) throw new Error('保护密钥不匹配或数据已被改动')
      return new Uint8Array([1, 2, 3])
    },
    readMetaRecord: async k => meta.get(k) || null,
    writeMetaRecord: async row => { meta.set(row.k, { ...row }) },
    generate: async (algorithm, options) => {
      calls.generated.push(algorithm)
      return addLocal(algorithm, { nodeId: options.nodeId })
    },
    registerSelfNodePublicKey: async (...args) => {
      const [algorithm, publicKey, securityLevel, fingerprint, keyId, version, rotate, headers] = args
      const pending = meta.get(`initialization/${node.nodeId}/${algorithm}`)
      assert(pending, 'public registration fields must be persisted before dispatch')
      assert.equal(pending.publicKey, publicKey)
      assert.equal(pending.keyId, keyId)
      assert.equal(pending.version, version)
      assert.equal(rotate, undefined)
      if (demo) {
        assert.equal(fingerprint, undefined)
        assert.equal(headers?.['X-Kms-Demo-Init-Lease'], 'lease-1')
      } else {
        assert.equal(fingerprint, 'device-fingerprint')
        assert.equal(headers, undefined)
      }
      assert.equal(securityLevel, pending.securityLevel)
      calls.registered.push(args)
      server.push({ algorithm, publicKey, keyId, keyVersion: version, allowsNewWork: true })
      node.keys[algorithm.toLowerCase()] = true
    },
    initSelfNodeKeys: async headers => {
      if (demo) assert.equal(headers?.['X-Kms-Demo-Init-Lease'], 'lease-1')
      calls.finished++
      node.status = 'ACTIVE'
    },
    acquireDemoInitLease: async () => { calls.leased++; return { leaseId: 'lease-1' } },
    releaseDemoInitLease: async id => { assert.equal(id, 'lease-1'); calls.released++ },
    hasDeviceKey: async () => { calls.device++; assert(!demo, 'Demo must not inspect device credentials'); return true },
    deviceFingerprint: async () => { calls.device++; assert(!demo, 'Demo must not fingerprint'); return 'device-fingerprint' },
    locks: { request: async (name, options, callback) => {
      assert.equal(name, `kms-init/${demo ? 'DEMO' : 'STANDALONE'}/${node.nodeId}`)
      assert.equal(options.ifAvailable, true)
      if (locked) return callback(null)
      locked = true
      try { return await callback({ name }) } finally { locked = false }
    } }
  }
  function addLocal(algorithm, fields = {}) {
    const keyId = fields.keyId || `${algorithm}-${local.length + 1}`
    const version = fields.version || 1
    const nodeId = fields.nodeId || node.nodeId
    const publicKey = algorithm === 'KYBER' ? 'ab'.repeat(1184) : 'abc123'
    const row = { algorithm, keyId, version, publicKey, nodeId, keyRef: `node/${nodeId}/${algorithm}/${keyId}/${version}`, ...fields }
    local.push(row)
    return { ...row }
  }
  function addRegistered(algorithm, fields = {}) {
    const key = addLocal(algorithm, fields)
    server.push({ algorithm, keyId: key.keyId, keyVersion: key.version, publicKey: key.publicKey, allowsNewWork: true })
    node.keys[algorithm.toLowerCase()] = true
    return key
  }
  return { deps, calls, node, local, server, meta, corrupt, addLocal, addRegistered,
    setContext: value => { context = value }, service: () => createNodeInitializationService(deps) }
}

for (const demo of [true, false]) {
  test(`${demo ? 'Demo' : 'Standalone'} generates only missing algorithms and is idempotent`, async () => {
    const f = fixture({ demo })
    const progress = []
    assert.equal((await f.service().initializeNode({ onProgress: row => progress.push(row) })).ready, true)
    assert.deepEqual(f.calls.generated, INITIALIZATION_ALGORITHMS)
    assert.equal(f.calls.finished, 1)
    assert.equal(f.calls.device, demo ? 0 : 2)
    assert.equal(f.meta.size, 4)
    for (const row of f.meta.values()) assert.deepEqual(Object.keys(row).sort(), ['algorithm', 'k', 'keyId', 'keyRef', 'publicKey', 'securityLevel', 'version'])
    assert.equal((await f.service().initializeNode()).ready, true)
    assert.equal(f.calls.generated.length, 4)
    assert.equal(f.calls.registered.length, 4)
    assert.equal(f.calls.finished, 1)
    assert.equal(f.calls.leased, demo ? 2 : 0)
    assert.equal(f.calls.released, demo ? 2 : 0)
    assert.equal(progress.at(-1).status, 'complete')
  })
}

test('failed registration reuses exact material/ref and skips previously completed algorithm', async () => {
  const f = fixture()
  const register = f.deps.registerSelfNodePublicKey
  let failed = false
  f.deps.registerSelfNodePublicKey = async (...args) => {
    if (args[0] === 'SSCL' && !failed) { failed = true; throw new Error('network interrupted') }
    return register(...args)
  }
  await assert.rejects(f.service().initializeNode(), /network interrupted/)
  const pending = { ...f.meta.get('initialization/Node-A/SSCL') }
  assert.deepEqual(f.calls.generated, ['KYBER', 'SSCL'])
  assert.equal(f.calls.released, 1)
  const progress = []
  await f.service().initializeNode({ onProgress: row => progress.push(row) })
  assert.deepEqual(f.calls.generated, INITIALIZATION_ALGORITHMS)
  assert.deepEqual(f.meta.get('initialization/Node-A/SSCL'), pending)
  assert.equal(progress[0].algorithm, 'KYBER')
  assert.match(progress[0].message, /跳过/)
})

test('lost successful registration response is reconciled rather than regenerated', async () => {
  const f = fixture()
  const register = f.deps.registerSelfNodePublicKey
  let lost = false
  f.deps.registerSelfNodePublicKey = async (...args) => {
    await register(...args)
    if (!lost) { lost = true; throw new Error('response lost') }
  }
  await assert.rejects(f.service().initializeNode(), /response lost/)
  await f.service().initializeNode()
  assert.deepEqual(f.calls.generated, INITIALIZATION_ALGORITHMS)
  assert.equal(f.calls.registered.length, 4)
})

for (const fault of ['missing', 'corrupt', 'mismatch', 'version']) {
  test(`ACTIVE ${fault} material fails closed without generation or registration`, async () => {
    const f = fixture({ status: 'ACTIVE' })
    const keys = INITIALIZATION_ALGORITHMS.map(algorithm => f.addRegistered(algorithm))
    if (fault === 'missing') f.local.splice(0, 1)
    if (fault === 'corrupt') f.corrupt.add(keys[0].keyRef)
    if (fault === 'mismatch') f.local[0].publicKey = 'different'
    if (fault === 'version') f.local[0].version = 2
    const inspection = await f.service().inspectInitialization()
    assert.equal(inspection.node.status, 'ACTIVE')
    assert.equal(inspection.ready, false)
    assert.equal(inspection.blocked, true)
    await assert.rejects(f.service().initializeNode())
    assert.equal(f.calls.generated.length, 0)
    assert.equal(f.calls.registered.length, 0)
    assert.equal(f.calls.finished, 0)
    assert.equal(f.calls.released, 1)
  })
}

test('PENDING reuses pre-existing unregistered materials and their public registration fields', async () => {
  const f = fixture()
  const key = f.addLocal('KYBER', { publicKey: 'ef'.repeat(800) })
  const before = { ...key }
  await f.service().initializeNode()
  assert.deepEqual(f.local[0], before)
  assert.deepEqual(f.calls.generated, ['SSCL', 'SM2', 'FALCON'])
  assert.equal(f.calls.registered[0][2], '512')
  assert.equal(f.meta.get('initialization/Node-A/KYBER').keyRef, key.keyRef)
})

test('missing pending metadata target blocks replacement, even before any registration', async () => {
  const f = fixture()
  f.meta.set('initialization/Node-A/KYBER', { algorithm: 'KYBER', keyRef: 'lost-ref', keyId: 'lost', version: 1, publicKey: 'pk' })
  await assert.rejects(f.service().initializeNode(), /待登记材料缺失/)
  assert.equal(f.calls.generated.length, 0)
})

test('registered but no longer usable versions are not replaced by first-init', async () => {
  const f = fixture()
  f.addRegistered('KYBER')
  f.server[0].allowsNewWork = false
  await assert.rejects(f.service().initializeNode(), /当前可用登记版本/)
  assert.equal(f.calls.generated.length, 0)
})

test('absent Web Locks and busy Web Locks both fail before lease/key generation', async () => {
  const f = fixture()
  f.deps.locks = undefined
  await assert.rejects(f.service().initializeNode(), /Web Locks/)
  f.deps.locks = { request: async (_name, _options, callback) => callback(null) }
  await assert.rejects(f.service().initializeNode(), /另一标签页/)
  assert.equal(f.calls.leased, 0)
  assert.equal(f.calls.generated.length, 0)
})

test('lease denial prevents local generation and public registration', async () => {
  const f = fixture()
  f.deps.acquireDemoInitLease = async () => { throw new Error('lease occupied') }
  await assert.rejects(f.service().initializeNode(), /lease occupied/)
  assert.equal(f.calls.generated.length, 0)
  assert.equal(f.meta.size, 0)
})

test('simultaneous attempts cannot both initialize the same node', async () => {
  const f = fixture()
  const first = f.service().initializeNode()
  const second = f.service().initializeNode()
  const results = await Promise.allSettled([first, second])
  assert.equal(results.filter(row => row.status === 'fulfilled').length, 1)
  assert.equal(results.filter(row => row.status === 'rejected').length, 1)
  assert.equal(f.calls.generated.length, 4)
  assert.equal(f.calls.leased, 1)
})

test('Demo context change during generation prevents registration and preserves pending material', async () => {
  const f = fixture()
  const generate = f.deps.generate
  f.deps.generate = async (...args) => {
    const row = await generate(...args)
    f.setContext({ principalType: 'ADMIN', revision: 2 })
    return row
  }
  await assert.rejects(f.service().initializeNode(), /身份已变化/)
  assert.equal(f.local.length, 1)
  assert.equal(f.meta.size, 1)
  assert.equal(f.calls.registered.length, 0)
  assert.equal(f.calls.released, 1)
})

test('ACTIVE readiness ignores historical locals and requires current exact identity', async () => {
  const f = fixture({ status: 'ACTIVE' })
  INITIALIZATION_ALGORITHMS.forEach(algorithm => f.addRegistered(algorithm))
  f.addLocal('KYBER', { keyId: 'historical', version: 4 })
  assert.equal((await f.service().inspectInitialization()).ready, true)
})

test('real browser crypto and encrypted IndexedDB resume after registration failure without changing refs', async () => {
  // In-memory IndexedDB only: this never reads or clears a real browser profile.
  const fake = await import(pathToFileURL(path.join(front, '../node_modules/fake-indexeddb/build/esm/index.js')).href)
  globalThis.indexedDB = new fake.IDBFactory()
  globalThis.location = { pathname: '/updatedel/demo/node/initialize' }
  const store = await import(pathToFileURL(path.join(front, 'utils/crypto/node-key-store.js')).href)
  const { cryptoProvider } = await import(pathToFileURL(path.join(front, 'utils/crypto/browser-provider.js')).href)
  assert.equal(store.DB_NAME, 'kms-demo-node-keystore')
  const f = fixture()
  f.deps.inspectNodeKeys = store.inspectNodeKeys
  f.deps.requireLocalKey = store.requireLocalKey
  f.deps.unsealSecret = store.unsealSecret
  f.deps.readMetaRecord = store.readMetaRecord
  f.deps.writeMetaRecord = async row => { await store.writeMetaRecord(row); f.meta.set(row.k, row) }
  f.deps.generate = async (algorithm, options) => {
    f.calls.generated.push(algorithm)
    return cryptoProvider.generate(algorithm, options)
  }
  const register = f.deps.registerSelfNodePublicKey
  let failed = false
  f.deps.registerSelfNodePublicKey = async (...args) => {
    if (!failed && args[0] === 'SSCL') { failed = true; throw new Error('simulated registration outage') }
    return register(...args)
  }
  await assert.rejects(f.service().initializeNode(), /simulated registration outage/)
  const interrupted = await store.inspectNodeKeys(f.node.nodeId)
  assert.equal(interrupted.keys.length, 2)
  const refs = interrupted.keys.map(row => row.keyRef)
  await f.service().initializeNode()
  const finished = await store.inspectNodeKeys(f.node.nodeId)
  assert.equal(finished.keys.length, 4)
  for (const ref of refs) assert(finished.keys.some(row => row.keyRef === ref))
  assert.deepEqual(f.calls.generated, INITIALIZATION_ALGORITHMS)
  assert.equal((await f.service().inspectInitialization()).ready, true)
  assert.equal((await store.listDeviceKeyRefs()).length, 0, 'Demo does not create device credentials')
})

for (const demo of [true, false]) {
  test(`shared API ${demo ? 'omits Demo deviceId' : 'preserves Standalone deviceId'} and carries lease headers`, async () => {
    const apiSource = await readFile(path.join(front, 'api/pqkds/node-self.js'), 'utf8')
    const calls = []
    globalThis.__initApiTest = { http: { post: async (...args) => { calls.push(args); return { data: { leaseId: 'lease-x' } } } } }
    const code = `const IS_DEMO=${demo}; const http=globalThis.__initApiTest.http; const unwrap=r=>r.data; const pqkdsBaseURL='';\n${apiSource.replace(/^import[^\n]*\n/gm, '')}`
    const api = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
    const headers = { 'X-Kms-Demo-Init-Lease': 'lease-x' }
    await api.registerSelfNodePublicKey('SM2', 'ab', undefined, 'device', 'id', 1, undefined, headers)
    assert.equal(Object.hasOwn(calls[0][1], 'deviceId'), !demo)
    assert.equal(calls[0][2].headers, headers)
    await api.initSelfNodeKeys(headers)
    assert.equal(calls[1][2].headers, headers)
    assert.equal((await api.acquireDemoInitLease()).leaseId, 'lease-x')
    await api.releaseDemoInitLease('lease-x')
    assert.deepEqual(calls[2].slice(0, 2), ['/node-self/demo-init/lease/', {}])
    assert.deepEqual(calls[3].slice(0, 2), ['/node-self/demo-init/release/', { leaseId: 'lease-x' }])
    delete globalThis.__initApiTest
  })
}
