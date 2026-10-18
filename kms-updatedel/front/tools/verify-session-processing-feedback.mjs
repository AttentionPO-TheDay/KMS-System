// Actual session handler, isolated dependencies. No live server or user keys.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { parse, babelParse } from '@vue/compiler-sfc'

const source = readFileSync(new URL('../src/views/selfSessions/index.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content
const ast = babelParse(script, { sourceType: 'module' })
const fn = ast.program.body.find(node => node.type === 'FunctionDeclaration' && node.id.name === 'handleProcess')
assert(!/处理会话|处理中止|progress\./.test(descriptor.template.content))
assert(!/\bmakeSteps\b|\btracker\b|const progress\b/.test(script))

const sequence = ['versions', 'envelopes', 'verify-local', 'private-key', 'unwrap', 'hash', 'store', 'verify-report', 'recover-report', 'proof', 'confirm', 'refresh']
const ref = value => ({ value })
for (const scenario of ['waiting', 'established', 'mismatch', ...sequence.filter(step => step !== 'refresh')]) {
  const calls = [], messages = []
  const key = new Uint8Array(16).fill(7)
  async function step(name, value) {
    calls.push(name)
    if (scenario === name) throw Error('测试失败：' + name)
    return value
  }
  const context = {
    Uint8Array, busySession: ref(''), selfNodeId: ref('B'), localKeySessions: ref(new Set()),
    ElMessage: { success: text => messages.push(['success', text]), error: text => messages.push(['error', text]) },
    describeError: error => error.message,
    getSessionVersions: () => step('versions', { falconPublicKey: 'public', recipientKeyId: 'recipient', recipientKeyVersion: 1, protectionAlgorithm: 'KYBER' }),
    listSelfEnvelopes: () => step('envelopes', { items: [{ sessionId: 'session', envelopeId: 1, envelope: { signature: 'signature' } }] }),
    verifyNodeEnvelope: () => step('verify-local', { ok: true }),
    buildKeyRef: () => 'local-ref', algorithmFromWrapping: () => 'KYBER',
    cryptoProvider: { hasKey: () => step('private-key', true) },
    unwrapNodeEnvelope: () => step('unwrap', key),
    checkRecoveredKeyHash: () => step('hash', { ok: true }),
    sealSessionSecret: async (sessionId, bytes) => {
      assert.equal(sessionId, 'session'); assert.equal(bytes.length, 16)
      await step('store')
    },
    verifyEnvelope: () => step('verify-report'), recoverEnvelope: () => step('recover-report'),
    sessionProofFromStore: () => step('proof', 'hmac'),
    confirmSelfSession: async (sessionId, proof) => {
      assert.equal(sessionId, 'session'); assert.equal(proof, 'hmac')
      return step('confirm', scenario === 'mismatch' ? { reason: 'PROOF_MISMATCH', msg: '双方证明不一致' }
        : scenario === 'established' ? { established: true, status: 'established' } : { established: false })
    },
    load: () => step('refresh'),
  }
  await vm.runInNewContext(`(${script.slice(fn.start, fn.end)})`, context)({ sessionId: 'session' })
  assert.equal(context.busySession.value, '', scenario)
  if (scenario === 'waiting' || scenario === 'established') {
    assert.deepEqual(calls, sequence)
    assert.equal(messages.length, 1)
    assert.deepEqual(messages[0], ['success', scenario === 'waiting' ? '本机处理完成，等待对方确认' : '会话已建立'])
    assert(context.localKeySessions.value.has('session'))
  } else {
    assert.equal(messages.length, 1)
    assert.equal(messages[0][0], 'error')
    if (scenario === 'mismatch') assert.match(messages[0][1], /双方证明不一致/)
    else {
      assert.match(messages[0][1], /测试失败/)
      assert.deepEqual(calls, sequence.slice(0, sequence.indexOf(scenario) + 1), 'no later operation after a failed step')
    }
    assert(!calls.includes('refresh'))
  }
  if (calls.includes('unwrap') && scenario !== 'unwrap') assert(key.every(byte => byte === 0), 'clear recovered K in success and failure paths')
  assert(!messages.some(([, text]) => text.includes('处理中止')))
}
console.log('PASS: process panel removed; waiting is normal success, established confirmation preserved, proof mismatch and every failed step reported, call order/storage/key zeroization unchanged')
