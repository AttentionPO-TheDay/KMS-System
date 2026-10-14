import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { generationAlgorithms, GENERATION_ALGORITHM_META } from '../src/utils/key-generation-purpose.js'
import { chainEvidenceText } from '../src/utils/node-chain-evidence.js'

assert.deepEqual(generationAlgorithms('protection'), ['KYBER', 'SSCL', 'SM2', 'FALCON_CL_V1'])
assert.deepEqual(generationAlgorithms('signing'), ['FALCON'])
assert.throws(() => generationAlgorithms('unknown'))
assert.equal(chainEvidenceText({ status: 'CONFIRMED', transactionValid: true, metadataMatches: true }), '已上链')
assert.notEqual(chainEvidenceText({ status: 'CONFIRMED' }), '已上链')
assert.notEqual(chainEvidenceText({ status: 'PENDING' }), '已上链')
assert.notEqual(chainEvidenceText(null), '已上链')
assert.match(GENERATION_ALGORITHM_META.FALCON.role, /不用于封装/)
assert.match(GENERATION_ALGORITHM_META.FALCON_CL_V1.role, /不用于签名/)

const source = readFileSync(new URL('../src/views/generate/create.vue', import.meta.url), 'utf8')
const sessions = readFileSync(new URL('../src/views/selfSessions/index.vue', import.meta.url), 'utf8')
for (const [filename, content] of [['create.vue', source], ['selfSessions.vue', sessions]]) {
  const { descriptor, errors } = parse(content, { filename })
  assert.deepEqual(errors, [])
  compileScript(descriptor, { id: filename })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename, id: filename }).errors, [])
}
assert.match(sessions, /purpose="signing"/)
assert.match(sessions, /会话签名密钥/)
assert.match(source, /filter\(row => allowedAlgorithms.value.includes\(row.algorithm\)\)/)
assert.doesNotMatch(source, /<FalconEncryptionSupplement/)

// Exercise the actual UI handler with TEST_ONLY service spies; no HTTP/production data.
const handler = source.slice(source.indexOf('async function handleGenerate(card)'), source.indexOf('async function runSelfTest('))
const calls = []
let cancelled = false
const context = {
  allowedAlgorithms: { value: generationAlgorithms('protection') }, generating: { value: '' },
  node: { value: { nodeId: 'TEST_ONLY_PURPOSE' } }, kyberVariant: { value: 768 }, selfTestResults: { value: {} },
  ElMessageBox: { confirm: async () => { if (cancelled) throw 'cancel' } },
  ElMessage: { success() {}, warning() {}, error(message) { throw new Error(message) } },
  load: async () => {}, describeError: String,
  generateAndRegisterNodeKey: async request => {
    calls.push(request)
    return { material: { keyRef: 'TEST_ONLY', keyId: 'test' }, check: { ok: true } }
  }
}
const generate = vm.runInNewContext(`${handler}; handleGenerate`, context)
await generate({ algorithm: 'FALCON_CL_V1', label: 'test' })
assert.equal(calls.at(-1).algorithm, 'FALCON_CL_V1')
assert.equal(calls.at(-1).rotate, undefined)
await assert.rejects(generate({ algorithm: 'FALCON' }), /当前页面/)
await generate({ algorithm: 'FALCON_CL_V1', label: 'test', active: { keyId: 'original', keyVersion: 2 } })
assert.equal(calls.at(-1).rotate, undefined)
assert.equal(calls.at(-1).keyId, undefined)
assert.equal(calls.at(-1).version, undefined) // workflow default is version 1 and a freshly minted keyId
cancelled = true
const before = calls.length
await generate({ algorithm: 'FALCON_CL_V1', label: 'test', active: { keyId: 'original', keyVersion: 2 } })
assert.equal(calls.length, before)
cancelled = false
context.allowedAlgorithms.value = generationAlgorithms('signing')
await generate({ algorithm: 'FALCON', label: 'standard signing' })
assert.equal(calls.at(-1).algorithm, 'FALCON')
await assert.rejects(generate({ algorithm: 'FALCON_CL_V1' }), /当前页面/)
console.log('PASS: generation purposes, Vue compilation, real handler algorithm routing, fresh CL generation (not rotation), cancellation and signing isolation')
