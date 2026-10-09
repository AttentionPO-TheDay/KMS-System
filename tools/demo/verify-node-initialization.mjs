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
const keyRefURL = pathToFileURL(path.join(front, 'utils/crypto/key-ref.js')).href
const schemeURL = pathToFileURL(path.join(front, 'utils/crypto/generation-scheme.js')).href
const NODE_SELF_ERR = { KEYGEN_AUTHORIZATION_EXPIRED: 'KEYGEN_AUTHORIZATION_EXPIRED', KEYGEN_GENERATION_REQUIRED: 'KEYGEN_GENERATION_REQUIRED' }
const moduleURL = `data:text/javascript;base64,${Buffer.from(`import {activeServerKey,findLocalKey,reconcileRow,RECONCILE} from '${compareURL}';\nimport {publicGeneration,publicGenerationContext,formatGenerationName,GENERATION_SCHEMES} from '${schemeURL}';\nimport {buildKeyRef} from '${keyRefURL}';\nconst NODE_SELF_ERR=${JSON.stringify(NODE_SELF_ERR)};\n${core}`).toString('base64')}`
const { createNodeInitializationService, INITIALIZATION_ALGORITHMS } = await import(moduleURL)

function fixture({ demo = true, status = 'PENDING_INIT' } = {}) {
  const node = { nodeId: 'Node-A', status, keys: {}, keygenIdentity: {
    userId: '42', nodeId: 'Node-A', bindingKind: demo ? 'DEMO' : 'DEVICE', deviceFingerprint: demo ? '' : 'device-fingerprint',
    demoSessionId: demo ? 'opaque-session-hash' : '', demoRevision: demo ? '1' : ''
  } }
  const local = []
  const server = []
  const meta = new Map()
  const calls = { generated: [], registered: [], issued: [], renewed: [], leased: 0, released: 0, finished: 0, device: 0 }
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
    listSelfNodeKeygenIssuances: async () => ({ issuances: [] }),
    issueSelfNodeKeygen: async (request, headers) => {
      if (demo && node.status === 'PENDING_INIT') assert.equal(headers?.['X-Kms-Demo-Init-Lease'], 'lease-1')
      if (!demo) assert.equal(request.deviceId, 'device-fingerprint')
      calls.issued.push({ request, headers })
      return issuance(request)
    },
    renewSelfNodeKeygenAuthorization: async (request, headers) => {
      calls.renewed.push({ request, headers })
      return { authorizationTicketId: `renewed-${calls.renewed.length}` }
    },
    updateGenerationAuthorization: async (ref, ticket) => {
      const row = local.find(key => key.keyRef === ref)
      row.generation = { ...row.generation, authorizationTicketId: ticket }
    },
    selfTest: async () => ({ ok: true, detail: 'fixture self-test' }),
    generate: async (algorithm, options) => {
      calls.generated.push(algorithm)
      const keyId = options.keyId || `${algorithm}-${local.length + 1}`
      const fields = { nodeId: options.nodeId, keyId, version: options.version || 1 }
      if (algorithm === 'KYBER' || algorithm === 'FALCON') {
        assert.deepEqual(options.generationContext, { nodeId: node.nodeId, ...node.keygenIdentity })
        const issued = await options.issueKeygen({ algorithm, nodeId: options.nodeId, keyId,
          keyVersion: fields.version, variant: algorithm === 'KYBER' ? (options.variant || 768) : 512 })
        fields.generation = { schemeId: issued.generationScheme, schemeVersion: 1,
          generationIssuanceId: issued.generationIssuanceId, authorizationTicketId: issued.authorizationTicketId }
        fields.generationContext = issued.context
      }
      return addLocal(algorithm, fields)
    },
    registerSelfNodePublicKey: async (...args) => {
      const [algorithm, publicKey, securityLevel, fingerprint, keyId, version, rotate, headers, options] = args
      if (algorithm === 'KYBER' || algorithm === 'FALCON') assert.equal(options.generation.schemeVersion, 1)
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
      server.push({ algorithm, publicKey, keyId, keyVersion: version, allowsNewWork: true, generation: options?.generation })
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
  function issuance(request) {
    const schemeId = request.algorithm === 'KYBER' ? 'KMS_SPLIT_KEM_V1' : 'KMS_SPLIT_SIGN_V1'
    const id = `issuance-${request.algorithm}-${request.keyId}-${request.keyVersion}`
    return { generationScheme: schemeId, generationIssuanceId: id, authorizationTicketId: `ticket-${id}`,
      share: Buffer.alloc(32, 37).toString('base64'), expiresAt: new Date(Date.now() + 600000).toISOString(),
      context: { schemeId, schemeVersion: '1', coreFamily: request.algorithm, variant: String(request.variant || 768),
        userId: '42', nodeId: node.nodeId, bindingKind: demo ? 'DEMO' : 'DEVICE',
        deviceFingerprint: demo ? '' : 'device-fingerprint', demoSessionId: demo ? 'opaque-session-hash' : '',
        demoRevision: demo ? String(context.revision) : '', keyId: request.keyId, keyVersion: String(request.keyVersion),
        purpose: request.algorithm === 'KYBER' ? 'KEM_KEYGEN' : 'SIGN_KEYGEN', generationIssuanceId: id } }
  }
  function addSplitLocal(algorithm, fields = {}) {
    const row = addLocal(algorithm, fields)
    const issued = issuance({ algorithm, keyId: row.keyId, keyVersion: row.version,
      variant: algorithm === 'FALCON' ? 512 : (row.publicKey.length === 1600 ? 512 : 768) })
    const actual = local.find(key => key.keyRef === row.keyRef)
    actual.generation = { schemeId: issued.generationScheme, schemeVersion: 1,
      generationIssuanceId: issued.generationIssuanceId, authorizationTicketId: issued.authorizationTicketId }
    actual.generationContext = issued.context
    return { ...actual }
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
  return { deps, calls, node, local, server, meta, corrupt, issuance, addLocal, addSplitLocal, addRegistered,
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
    for (const row of f.meta.values()) {
      const expected = ['algorithm', 'k', 'keyId', 'keyRef', 'publicKey', 'securityLevel', 'version']
      if (row.algorithm === 'KYBER' || row.algorithm === 'FALCON') expected.push('generation', 'generationContext')
      assert.deepEqual(Object.keys(row).sort(), expected.sort())
      assert(!JSON.stringify(row).includes('share'), 'no contributions enter public pending')
    }
    assert.equal(f.calls.issued.length, 2)
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
  const key = f.addSplitLocal('KYBER', { publicKey: 'ef'.repeat(800) })
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
  await assert.rejects(f.service().initializeNode(), /身份修订已变化/)
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
  f.deps.updateGenerationAuthorization = store.updateGenerationAuthorization
  f.deps.generate = async (algorithm, options) => {
    f.calls.generated.push(algorithm)
    return cryptoProvider.generate(algorithm, options)
  }
  const register = f.deps.registerSelfNodePublicKey
  let failed = false
  let expired = false
  f.deps.registerSelfNodePublicKey = async (...args) => {
    if (!expired && args[0] === 'KYBER') {
      expired = true
      throw Object.assign(new Error('expired actual sealed key authorization'), { errorCode: 'KEYGEN_AUTHORIZATION_EXPIRED' })
    }
    if (!failed && args[0] === 'SSCL') { failed = true; throw new Error('simulated registration outage') }
    return register(...args)
  }
  await assert.rejects(f.service().initializeNode(), /simulated registration outage/)
  const interrupted = await store.inspectNodeKeys(f.node.nodeId)
  assert.equal(interrupted.keys.length, 2)
  assert.equal(interrupted.keys.find(row => row.algorithm === 'KYBER').generation.authorizationTicketId, 'renewed-1')
  assert.equal(f.calls.renewed.length, 1)
  const refs = interrupted.keys.map(row => row.keyRef)
  await f.service().initializeNode()
  const finished = await store.inspectNodeKeys(f.node.nodeId)
  assert.equal(finished.keys.length, 4)
  for (const ref of refs) assert(finished.keys.some(row => row.keyRef === ref))
  assert.deepEqual(f.calls.generated, INITIALIZATION_ALGORITHMS)
  assert.equal((await f.service().inspectInitialization()).ready, true)
  assert.equal((await store.listDeviceKeyRefs()).length, 0, 'Demo does not create device credentials')
  // Verify actual newly generated bytes, not only passing fixture crypto.
  for (const row of finished.keys.filter(key => ['KYBER', 'FALCON'].includes(key.algorithm))) {
    assert.equal(row.generation.schemeVersion, 1)
    assert.equal(row.generationContext.nodeId, f.node.nodeId)
    assert.equal((await cryptoProvider.selfTest(row.algorithm, row.keyRef)).ok, true)
  }
})

test('KGC issuance failure fails closed before sealing, registration or public source label', async () => {
  const f = fixture()
  f.deps.issueSelfNodeKeygen = async () => { throw Object.assign(new Error('双份额生成尚未启用'), { errorCode: 'KEYGEN_POLICY_DISABLED' }) }
  await assert.rejects(f.service().initializeNode(), error => error.errorCode === 'KEYGEN_POLICY_DISABLED')
  assert.equal(f.local.length, 0)
  assert.equal(f.meta.size, 0)
  assert.equal(f.calls.registered.length, 0)
})

test('old unregistered PQ materials require explicit historical recovery without relabel or replacement', async () => {
  const f = fixture()
  const old = f.addLocal('KYBER')
  const inspected = await f.service().inspectInitialization()
  assert.equal(inspected.algorithms[0].state, 'LEGACY_RECOVERY_REQUIRED')
  await assert.rejects(f.service().initializeNode(), /历史未登记材料/)
  assert.equal(f.calls.generated.length, 0)
  assert.equal(f.calls.issued.length, 0)
  assert.deepEqual(f.local[0], old)
  assert.equal(f.meta.size, 0)
})

test('sealed-before-pending crash rebuilds public pending and never issues fresh entropy', async () => {
  const f = fixture()
  const sealed = f.addSplitLocal('KYBER')
  assert.equal(f.meta.size, 0)
  const inspection = await f.service().inspectInitialization()
  assert.equal(inspection.blocked, false)
  assert.deepEqual(f.meta.get('initialization/Node-A/KYBER').generation, sealed.generation)
  await f.service().initializeNode()
  assert.equal(f.calls.generated.includes('KYBER'), false)
  assert.equal(f.calls.issued.filter(call => call.request.algorithm === 'KYBER').length, 0)
  assert.equal(f.calls.registered[0][1], sealed.publicKey)
})

test('expired authorization renews the same sealed public key/original issuance without another KeyGen', async () => {
  const f = fixture()
  const register = f.deps.registerSelfNodePublicKey
  let expired = false
  f.deps.registerSelfNodePublicKey = async (...args) => {
    if (!expired) { expired = true; throw Object.assign(new Error('expired'), { errorCode: 'KEYGEN_AUTHORIZATION_EXPIRED' }) }
    return register(...args)
  }
  await f.service().initializeNode()
  assert.deepEqual(f.calls.generated, INITIALIZATION_ALGORITHMS)
  assert.equal(f.calls.issued.length, 2)
  assert.equal(f.calls.renewed.length, 1)
  const key = f.local.find(row => row.algorithm === 'KYBER')
  assert.equal(f.calls.renewed[0].request.publicKey, key.publicKey)
  assert.equal(f.calls.renewed[0].request.generationIssuanceId, key.generation.generationIssuanceId)
  assert.equal(f.calls.renewed[0].headers['X-Kms-Demo-Init-Lease'], 'lease-1')
  assert.equal(key.generation.authorizationTicketId, 'renewed-1')
  assert.equal(f.meta.get('initialization/Node-A/KYBER').generation.authorizationTicketId, 'renewed-1')
})

for (const errorCode of ['KEYGEN_CONTEXT_MISMATCH', 'KEYGEN_PUBLIC_KEY_CONFLICT', 'KEYGEN_AUTHORIZATION_SUPERSEDED']) {
  test(`${errorCode} never silently renews, repairs identity or regenerates sealed material`, async () => {
    const f = fixture()
    f.deps.registerSelfNodePublicKey = async () => { throw Object.assign(new Error(errorCode), { errorCode }) }
    await assert.rejects(f.service().initializeNode(), error => error.errorCode === errorCode)
    const sealed = { ...f.local[0] }
    await assert.rejects(f.service().initializeNode(), error => error.errorCode === errorCode)
    assert.equal(f.calls.generated.length, 1)
    assert.equal(f.calls.issued.length, 1)
    assert.equal(f.calls.renewed.length, 0)
    assert.deepEqual(f.local[0], sealed)
  })
}

test('new creation retries recovered sealed material even when pending write failed', async () => {
  const f = fixture({ status: 'ACTIVE' })
  const write = f.deps.writeMetaRecord
  let fail = true
  f.deps.writeMetaRecord = async row => { if (fail) { fail = false; throw new Error('pending commit failed') }; return write(row) }
  f.deps.registerSelfNodePublicKey = async (...args) => { f.calls.registered.push(args); return { keyId: args[4], keyVersion: args[5] } }
  await assert.rejects(f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER', variant: 768 }), /pending commit failed/)
  const before = { ...f.local[0] }
  const done = await f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER', variant: 1024 })
  assert.equal(done.reused, true)
  assert.equal(done.material.keyRef, before.keyRef)
  assert.equal(done.material.publicKey, before.publicKey)
  assert.equal(f.calls.generated.length, 1)
  assert.equal(f.calls.issued.length, 1)
  assert.equal(f.calls.registered[0][2], '768', 'recovery uses sealed variant, never new selector')
})

test('rotation reuses sealed next version with source references and no new KGC entropy', async () => {
  const f = fixture({ status: 'ACTIVE' })
  const current = f.addRegistered('KYBER', { keyId: 'stable' })
  const next = f.addSplitLocal('KYBER', { keyId: current.keyId, version: 2 })
  f.deps.registerSelfNodePublicKey = async (...args) => { f.calls.registered.push(args); return { keyId: args[4], keyVersion: args[5] } }
  const done = await f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER', keyId: current.keyId, version: 2, variant: 768, rotate: true })
  assert.equal(done.reused, true)
  assert.deepEqual(done.material.generation, next.generation)
  assert.equal(f.calls.generated.length, 0)
  assert.equal(f.calls.issued.length, 0)
  assert.equal(f.calls.registered[0][6], true)
  assert.deepEqual(f.calls.registered[0][8].generation, next.generation)
})

for (const rotate of [false, true]) {
  test(`${rotate ? 'rotation' : 'creation'} missing pending target blocks replacement before KGC issuance`, async () => {
    const f = fixture({ status: 'ACTIVE' })
    if (rotate) f.addRegistered('KYBER', { keyId: 'stable' })
    f.meta.set(rotate ? 'rotation/node/Node-A/KYBER/stable/2' : 'initialization/Node-A/KYBER',
      { keyRef: 'node/Node-A/KYBER/stable/2', algorithm: 'KYBER', keyId: 'stable', version: 2, publicKey: 'missing' })
    await assert.rejects(f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER',
      ...(rotate ? { keyId: 'stable', version: 2, rotate: true } : {}) }), /待登记材料缺失/)
    assert.equal(f.calls.issued.length, 0)
    assert.equal(f.calls.generated.length, 0)
  })
}



function recoveryRecord(f, { keyId = 'lost-issuance-key', version = 1, variant = 768 } = {}) {
  const issued = f.issuance({ algorithm: 'KYBER', keyId, keyVersion: version, variant })
  return { generationIssuanceId: issued.generationIssuanceId, context: issued.context,
    status: 'ISSUED', publicKeyHash: '', authorizationTicketId: issued.authorizationTicketId,
    authorizationStatus: 'ISSUED', expiresAt: issued.expiresAt }
}

test('lost issuance response is publicly discoverable and requires explicit abandon confirmation before replacement', async () => {
  const f = fixture()
  let original
  const issue = f.deps.issueSelfNodeKeygen
  f.deps.listSelfNodeKeygenIssuances = async (_fingerprint, headers) => {
    assert.equal(headers['X-Kms-Demo-Init-Lease'], 'lease-1')
    return { issuances: original?.status === 'ISSUED' ? [original] : [] }
  }
  f.deps.issueSelfNodeKeygen = async (request, headers) => {
    const issued = await issue(request, headers)
    if (!original) {
      original = { generationIssuanceId: issued.generationIssuanceId, context: issued.context,
        status: 'ISSUED', publicKeyHash: '', authorizationTicketId: issued.authorizationTicketId,
        authorizationStatus: 'ISSUED', expiresAt: issued.expiresAt }
      throw new Error('issuance response lost')
    }
    if (request.algorithm === 'KYBER') {
      assert.equal(request.abandonGenerationIssuanceId, original.generationIssuanceId)
      assert.equal(request.keyId, original.context.keyId)
      original.status = 'ABANDONED'
      return { ...issued, generationIssuanceId: 'replacement-issuance', authorizationTicketId: 'replacement-ticket',
        context: { ...issued.context, generationIssuanceId: 'replacement-issuance' } }
    }
    return issued
  }
  await assert.rejects(f.service().initializeNode(), /issuance response lost/)
  assert.equal(f.local.length, 0)
  const confirmed = []
  await f.service().initializeNode({ confirmUnusedIssuance: async record => { confirmed.push(record); return true } })
  assert.equal(confirmed.length, 1)
  assert.match(confirmed[0].message, /原秘密份额无法恢复/)
  const sealed = f.local.find(row => row.algorithm === 'KYBER')
  assert.equal(sealed.keyId, original.context.keyId)
  assert.equal(sealed.generation.generationIssuanceId, 'replacement-issuance')
  assert.equal(original.status, 'ABANDONED')
})

for (const entry of ['initialization', 'creation', 'rotation']) {
  test(`${entry} cancels unused-issuance recovery without issuing new entropy or sealing another key`, async () => {
    const f = fixture({ status: entry === 'initialization' ? 'PENDING_INIT' : 'ACTIVE' })
    if (entry === 'rotation') f.addRegistered('KYBER', { keyId: 'stable' })
    const record = recoveryRecord(f, entry === 'rotation' ? { keyId: 'stable', version: 2 } : {})
    f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [record] })
    let confirms = 0
    const confirmUnusedIssuance = async () => { confirms++; return false }
    const operation = entry === 'initialization' ? f.service().initializeNode({ confirmUnusedIssuance })
      : f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER', variant: 768,
        ...(entry === 'rotation' ? { keyId: 'stable', version: 2, rotate: true } : {}), confirmUnusedIssuance })
    await assert.rejects(operation, /已取消弃用原始签发/)
    assert.equal(confirms, 1)
    assert.equal(f.calls.issued.length, 0)
    assert.equal(f.calls.registered.length, 0)
    assert.equal(f.local.length, entry === 'rotation' ? 1 : 0)
  })
}

test('explicit fixed-version rotation recovers lost issuance while preserving keyId/version/variant', async () => {
  const f = fixture({ status: 'ACTIVE' })
  f.addRegistered('KYBER', { keyId: 'stable' })
  const record = recoveryRecord(f, { keyId: 'stable', version: 2 })
  f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [record] })
  f.deps.registerSelfNodePublicKey = async (...args) => { f.calls.registered.push(args); return { keyId: args[4], keyVersion: args[5] } }
  const done = await f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER',
    keyId: 'stable', version: 2, variant: 768, rotate: true, confirmUnusedIssuance: async () => true })
  assert.equal(done.material.keyId, 'stable')
  assert.equal(done.material.version, 2)
  assert.equal(f.calls.issued[0].request.abandonGenerationIssuanceId, record.generationIssuanceId)
  assert.equal(f.calls.issued[0].request.variant, 768)
  assert.equal(f.calls.registered[0][6], true)
})

for (const fault of ['BOUND', 'prebound']) {
  test(`${fault} issuance is never offered for abandonment or silently replaced`, async () => {
    const f = fixture({ status: 'ACTIVE' })
    f.addRegistered('KYBER', { keyId: 'stable' })
    const record = recoveryRecord(f, { keyId: 'stable', version: 2 })
    if (fault === 'BOUND') record.status = 'BOUND'
    else record.publicKeyHash = 'public-key-already-prebound'
    f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [record] })
    f.deps.issueSelfNodeKeygen = async request => {
      assert.equal(request.abandonGenerationIssuanceId, undefined)
      throw Object.assign(new Error('existing issuance conflict'), { errorCode: 'KEYGEN_ISSUANCE_CONFLICT' })
    }
    let confirmed = false
    await assert.rejects(f.service().generateAndRegisterNodeKey({ nodeId: f.node.nodeId, algorithm: 'KYBER',
      keyId: 'stable', version: 2, variant: 768, rotate: true, confirmUnusedIssuance: async () => { confirmed = true; return true } }), /conflict/)
    assert.equal(confirmed, false)
    assert.equal(f.local.length, 1)
  })
}

test('recovery identity mismatch is rejected before generation or confirmation', async () => {
  const f = fixture()
  const record = recoveryRecord(f)
  record.context.userId = '99'
  f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [record] })
  await assert.rejects(f.service().initializeNode({ confirmUnusedIssuance: async () => { assert.fail('must not ask to abandon another identity') } }), /清单与当前可信身份不一致/)
  assert.equal(f.calls.generated.length, 0)
  assert.equal(f.calls.issued.length, 0)
})

test('identity changes during confirmation prevent abandon/issuance and preserve all local records', async () => {
  const f = fixture()
  f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [recoveryRecord(f)] })
  await assert.rejects(f.service().initializeNode({ confirmUnusedIssuance: async () => {
    f.setContext({ principalType: 'ADMIN', revision: 2 }); return true
  } }), /身份修订已变化/)
  assert.equal(f.calls.issued.length, 0)
  assert.equal(f.local.length, 0)
})

test('a sealed record appearing during confirmation blocks abandonment and overwriting', async () => {
  const f = fixture()
  const record = recoveryRecord(f)
  f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [record] })
  let original
  await assert.rejects(f.service().initializeNode({ confirmUnusedIssuance: async () => {
    original = f.addSplitLocal('KYBER', { keyId: record.context.keyId }); return true
  } }), /已有本机封存或待登记记录/)
  assert.equal(f.calls.issued.length, 0)
  assert.deepEqual(f.local[0], original)
})

for (const demo of [true, false]) {
  test(`${demo ? 'Demo' : 'Standalone'} trusted identity change after issuance aborts before sealing and registration`, async () => {
    const f = fixture({ demo })
    const issue = f.deps.issueSelfNodeKeygen
    f.deps.issueSelfNodeKeygen = async (...args) => {
      const issued = await issue(...args)
      f.node.keygenIdentity = { ...f.node.keygenIdentity, userId: '99' }
      return issued
    }
    await assert.rejects(f.service().initializeNode(), /可信生成身份上下文已变化/)
    assert.equal(f.calls.issued.length, 1)
    assert.equal(f.local.length, 0)
    assert.equal(f.calls.registered.length, 0)
  })
}

test('complete trusted snapshot is mandatory before a new PQ generation callback', async () => {
  const f = fixture()
  f.node.keygenIdentity = null
  await assert.rejects(f.service().initializeNode(), /未提供完整可信生成身份快照/)
  assert.equal(f.calls.generated.length, 0)
  assert.equal(f.calls.issued.length, 0)
})

for (const keyVersion of ['01', '1e3', '9007199254740993']) {
  test(`invalid recovery version ${keyVersion} is rejected before numeric keyRef construction/confirmation`, async () => {
    const f = fixture()
    const record = recoveryRecord(f)
    record.context.keyVersion = keyVersion
    f.deps.listSelfNodeKeygenIssuances = async () => ({ issuances: [record] })
    await assert.rejects(f.service().initializeNode({ confirmUnusedIssuance: async () => assert.fail('invalid version must not be offered') }))
    assert.equal(f.calls.generated.length, 0)
    assert.equal(f.calls.issued.length, 0)
  })
}

test('identity changes after sealing/pending prevent public registration and retry never regenerates', async () => {
  const f = fixture()
  const write = f.deps.writeMetaRecord
  let changed = false
  f.deps.writeMetaRecord = async row => {
    await write(row)
    if (!changed) { changed = true; f.node.keygenIdentity = { ...f.node.keygenIdentity, userId: '99' } }
  }
  await assert.rejects(f.service().initializeNode(), /可信生成身份上下文已变化/)
  assert.equal(f.local.length, 1)
  assert.equal(f.calls.registered.length, 0)
  await assert.rejects(f.service().initializeNode(), /已封存密钥属于不同身份/)
  assert.equal(f.calls.generated.length, 1)
  assert.equal(f.calls.issued.length, 1)
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
