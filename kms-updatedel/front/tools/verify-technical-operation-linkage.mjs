// Run the actual page handlers against isolated service spies. No live API / DB.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { parse, babelParse } from '@vue/compiler-sfc'
import {
  createTechnicalTrace, startTechnicalTrace, setTechnicalStage,
  progressTechnicalStage, recordTechnicalTrace, finishTechnicalTrace
} from '../src/utils/technical-operation-trace.js'

function handler(page, name, context) {
  const { descriptor } = parse(readFileSync(`src/views/${page}/index.vue`, 'utf8'))
  const script = descriptor.scriptSetup.content
  const ast = babelParse(script, { sourceType: 'module' })
  const node = ast.program.body.find(item => item.type === 'FunctionDeclaration' && item.id.name === name)
  assert(node, name)
  return vm.runInNewContext(`(${script.slice(node.start, node.end)})`, context)
}
const ref = value => ({ value })
function presentation(kind) {
  const trace = createTechnicalTrace()
  return { trace, technicalFlow: ref({
    start: (values, options = {}) => startTechnicalTrace(trace, values, options.mode === 'pool' ? 'pool' : kind),
    stage: (...args) => setTechnicalStage(trace, ...args),
    progress: (...args) => progressTechnicalStage(trace, ...args),
    record: (...args) => recordTechnicalTrace(trace, ...args),
    finish: (...args) => finishTechnicalTrace(trace, ...args)
  }) }
}
const state = (trace, id) => trace.stages.find(stage => stage.id === id).status
const messages = { success() {}, warning() {}, error() {} }
function held() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
// Drain microtasks only; these assertions do not depend on animation timers.
async function until(check) {
  for (let i = 0; i < 100; i++) { if (check()) return; await Promise.resolve() }
  assert(check(), 'handler did not reach expected await boundary')
}

async function preallocationCase(failUpload = false) {
  const { trace, technicalFlow } = presentation('preallocation')
  const peer = held(), wrap = held(), upload = held()
  let wraps = 0, signs = 0, uploads = 0
  const context = {
    technicalFlow, canSubmit: ref(true), submitting: ref(false), result: ref(null),
    selfNodeId: ref('NODE-A'), form: { nodeCode: 'NODE-B', count: 3, ttlHours: 1 },
    crypto, Uint8Array, performance, toHex: () => 'isolated-pool',
    cryptoProvider: {}, falconKey: ref({ keyId: 'signer', keyVersion: 1, keyRef: 'local' }),
    chunkSize: 2, ElMessage: messages, fetchPeerKyberKey: () => peer.promise,
    generatePayloadKey: () => new Uint8Array([1, 2]),
    buildNodeEnvelope: async () => { wraps++; if (wraps === 1) await wrap.promise; return { envelope: {}, keyHash: 'hash' } },
    signNodeEnvelope: async () => { signs++; return 'signature' },
    sealPoolSecret: async () => {},
    markPoolSecretsUploaded: async () => {},
    preallocatePool: async payload => {
      uploads++
      assert.equal(payload.poolId, 'pool_isolated-pool')
      if (uploads === 1) return upload.promise
      if (failUpload) throw Error('isolated upload interruption')
      return { generated: 0, failed: [{ index: 0 }], serverMs: 1 }
    }
  }
  const running = handler('preallocate', 'submit', context)()
  assert.equal(state(trace, 'peer'), 'running')
  assert.equal(state(trace, 'prepare'), 'pending')
  peer.resolve({ keyId: 'recipient', keyVersion: 2, publicKey: 'public' })
  await until(() => wraps === 1)
  assert.equal(state(trace, 'peer'), 'success')
  assert.equal(state(trace, 'prepare'), 'running')
  assert.equal(trace.facts.generated, 1)
  assert.equal(trace.facts.wrapped, 0)
  assert.equal(signs, 0)
  assert.equal(state(trace, 'submit'), 'pending')
  wrap.resolve()
  await until(() => uploads === 1)
  assert.equal(trace.facts.generated, 3)
  assert.equal(trace.facts.wrapped, 3)
  assert.equal(trace.facts.signed, 3)
  assert.equal(trace.facts.uploaded, 0)
  assert.equal(state(trace, 'submit'), 'running')
  upload.resolve({ generated: 2, failed: [], serverMs: 1 })
  await running
  assert.equal(trace.facts.accepted, 2)
  assert.equal(context.submitting.value, false)
  if (failUpload) {
    assert.equal(trace.status, 'failed')
    assert.equal(trace.facts.uploaded, 2, 'do not claim the failed request was accepted')
    assert.equal(state(trace, 'prepare'), 'success')
    assert.equal(state(trace, 'submit'), 'failed')
  } else {
    assert.equal(trace.status, 'partial')
    assert.equal(trace.facts.uploaded, 3)
    assert.equal(trace.facts.rejected, 1)
    assert.equal(context.result.value.failed[0].index, 2)
  }
}
await preallocationCase()
await preallocationCase(true)

async function distributionCase(pool, storageFailure) {
  const { trace, technicalFlow } = presentation('distribution')
  const first = held(), sign = held(), submit = held(), store = held()
  const entered = new Set()
  const context = {
    technicalFlow, canSubmit: ref(true), poolAvailable: ref(true), submitting: ref(false),
    errorMessage: ref(''), result: ref(null), selfNodeId: ref('NODE-A'),
    form: { receiverNodeCode: 'NODE-B', recipientKeyRef: 'recipient-v2', protectionAlgorithm: 'KYBER', expiresInHours: 1 },
    parseKeyRef: () => ({ keyId: 'recipient', keyVersion: 2 }),
    usablePeerKeys: ref([{ keyId: 'recipient', keyVersion: 2, publicKey: 'public' }]),
    falconKey: ref({ keyId: 'signer', keyVersion: 1 }), cryptoProvider: {},
    PROTECTION_LABELS: { KYBER: 'Kyber' }, ElMessage: messages,
    newBatchId: () => 'isolated-batch', generatePayloadKey: () => new Uint8Array([1, 2]),
    buildNodeEnvelope: () => { entered.add('first'); return first.promise },
    consumePoolItem: () => { entered.add('first'); return first.promise },
    signNodeEnvelope: () => { entered.add('sign'); return sign.promise },
    signPoolEnvelope: () => { entered.add('submit'); return submit.promise },
    createNodeDistribution: () => { entered.add('submit'); return submit.promise },
    sealSessionSecret: () => { entered.add('store'); return store.promise },
    nextLocalPoolSecret: async () => ({ poolId: 'isolated-pool', keyHash: 'isolated-hash' }),
    bindPoolSecretToSession: (values, sessionId) => {
      assert.equal(values.nodeId, 'NODE-A'); assert.equal(values.peerNodeId, 'NODE-B')
      assert.equal(values.poolId, 'isolated-pool'); assert.equal(sessionId, 'isolated-session')
      entered.add('store'); return store.promise
    },
    loadBatches: async () => {}, loadPoolSummary: async () => {}, loadPeerKeys: async () => {},
    describeError: error => error.message
  }
  const running = handler('distribute', pool ? 'handleDistributeFromPool' : 'handleDistribute', context)()
  assert.equal(state(trace, pool ? 'consume' : 'wrap'), 'running')
  assert.equal(state(trace, 'sign'), 'pending')
  if (pool) {
    assert(!trace.stages.some(stage => stage.id === 'wrap' || stage.id === 'prepare'))
    first.resolve({ sessionId: 'isolated-session', recipientKeyId: 'recipient', recipientKeyVersion: 2, remaining: 7,
      envelope: {}, envelopeId: 'isolated-envelope', poolId: 'isolated-pool', keyHash: 'isolated-hash' })
  } else first.resolve({ envelope: {}, keyHash: 'hash', wrapping: 'KYBER' })
  await until(() => entered.has('sign'))
  assert.equal(state(trace, pool ? 'consume' : 'wrap'), 'success')
  assert.equal(state(trace, 'sign'), 'running')
  assert.equal(state(trace, 'submit'), 'pending')
  sign.resolve('signature')
  await until(() => entered.has('submit'))
  assert.equal(state(trace, 'sign'), 'success')
  assert.equal(state(trace, 'submit'), 'running')
  assert.equal(state(trace, 'store'), 'pending')
  submit.resolve({ batchId: 'isolated-batch', sessionId: 'isolated-session', sessionStatus: 'initiated' })
  await until(() => entered.has('store'))
  assert.equal(state(trace, 'submit'), 'success')
  assert.equal(state(trace, 'store'), 'running')
  assert.equal(trace.facts.sessionId, 'isolated-session')
  if (storageFailure) store.reject(Error('isolated storage failure'))
  else store.resolve()
  await running
  assert.equal(context.submitting.value, false)
  assert.equal(trace.status, storageFailure ? 'partial' : 'success')
  assert.equal(state(trace, 'submit'), 'success')
  assert.equal(state(trace, 'store'), storageFailure ? 'partial' : 'success')
  assert.equal(trace.facts.sessionStatus, 'initiated')
  assert.equal(trace.facts.keyStored, !storageFailure)
  assert(!JSON.stringify(trace).includes('0102'), 'never disclose key material in a trace')
}
for (const pool of [false, true]) for (const failure of [false, true]) await distributionCase(pool, failure)

// Page wiring must wait for a fresh, successful reconciliation, not only a POST.
for (const reconciled of [false, true]) {
  const { trace, technicalFlow } = presentation('update')
  const refresh = held()
  const context = {
    technicalFlow, updating: ref(''), node: ref({ nodeId: 'NODE-A' }), lastRotate: ref(null), selfTestResults: ref({}),
    variantOf: () => 768, formatGenerationName: () => 'Kyber', ElMessage: messages, ElMessageBox: {}, RECONCILE: { MATCH: 'MATCH' },
    cards: ref([]), load: () => refresh.promise,
    generateAndRegisterNodeKey: async ({ onStage, keyId, version, rotate }) => {
      assert.equal(rotate, true); assert.equal(keyId, 'recipient'); assert.equal(version, 3)
      for (const id of ['identity', 'material', 'selftest', 'register']) onStage({ id, status: 'success', label: id })
      return { material: { keyId, version, keyRef: 'sealed' }, result: { keyId, keyVersion: version }, check: { ok: true } }
    }
  }
  const running = handler('keyupdate', 'handleRotate', context)({ algorithm: 'KYBER', label: 'Kyber', active: { keyId: 'recipient', keyVersion: 2 } })
  await until(() => state(trace, 'refresh') === 'running')
  assert.equal(trace.status, 'running')
  context.cards.value = [{ algorithm: 'KYBER', active: { keyId: 'recipient', keyVersion: 3 }, reconcile: { state: reconciled ? 'MATCH' : 'MISMATCH' } }]
  refresh.resolve()
  await running
  assert.equal(state(trace, 'refresh'), reconciled ? 'success' : 'partial')
  assert.equal(trace.status, reconciled ? 'success' : 'partial')
}

// Trace state machine: allowlisted scalars, no invented completion, bounded history.
{
  const { trace, technicalFlow } = presentation('update')
  const flow = technicalFlow.value
  flow.start({ secretKey: 'PRIVATE', keyHex: 'PRIVATE', nodeId: 'N'.repeat(200), requested: Infinity })
  assert.equal(trace.facts.nodeId.length, 160)
  assert.equal(trace.facts.requested, undefined)
  flow.stage('identity', 'running', 'pending actual response')
  flow.finish('failed', 'interrupted')
  assert.equal(state(trace, 'identity'), 'failed')
  assert.equal(state(trace, 'material'), 'pending')
  flow.stage('identity', 'success', 'late response')
  flow.progress('identity', { accepted: 100 })
  assert.equal(state(trace, 'identity'), 'failed')
  assert.equal(trace.facts.accepted, undefined)
  flow.start({ keyId: 'new' })
  assert.equal(trace.facts.nodeId, undefined)
  for (let i = 0; i < 1000; i++) flow.record('event')
  assert.equal(trace.events.length, 40)
  flow.finish('success', 'not all stages have executed')
  assert.equal(trace.status, 'partial')
  assert(!JSON.stringify(trace).includes('PRIVATE'))
}
console.log('PASS: actual page handlers await real stage boundaries, counts/partial receipts, both distribution paths, storage failure and version reconciliation')
