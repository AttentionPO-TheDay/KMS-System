// Isolated regression: execute the actual Vue handlers, never call a live API.
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import { parse, babelParse } from '@vue/compiler-sfc'

const ref = value => ({ value })
const frontend = fileURLToPath(new URL('../', import.meta.url))
const chainWarning = '已取用，但链上存证未成功（链不可用或未配置）'
function handler(page, name, context) {
  const script = parse(readFileSync(join(frontend, `src/views/${page}/index.vue`), 'utf8')).descriptor.scriptSetup.content
  const ast = babelParse(script, { sourceType: 'module' })
  const node = ast.program.body.find(item => item.type === 'FunctionDeclaration' && item.id.name === name)
  assert(node, name)
  return vm.runInNewContext(`(${script.slice(node.start, node.end)})`, context)
}
function messages() {
  const calls = []
  const ElMessage = Object.fromEntries(['success', 'warning', 'error', 'info'].map(type => [type, text => calls.push({ type, text })]))
  return { calls, ElMessage }
}
function noChainToast(calls) {
  assert(!calls.some(call => /链|存证/.test(call.text)), JSON.stringify(calls))
  assert(!calls.some(call => call.type === 'warning'), JSON.stringify(calls))
}

for (const apiFailure of [false, true]) {
  const { calls, ElMessage } = messages()
  const context = {
    technicalFlow: ref(null), submitting: ref(false), poolAvailable: ref(true),
    result: ref(null), errorMessage: ref(''), selfNodeId: ref('A'),
    form: { receiverNodeCode: 'B' }, falconKey: ref({ keyId: 'signer', keyVersion: 1, keyRef: 'ref' }),
    newBatchId: () => 'delivery', cryptoProvider: {}, PROTECTION_LABELS: { KYBER: 'Kyber' }, ElMessage,
    nextLocalPoolSecret: async () => ({ poolId: 'pool', keyHash: 'hash' }),
    consumePoolItem: async () => {
      if (apiFailure) throw Error('资源不可用')
      return { poolId: 'pool', keyHash: 'hash', sessionId: 'session', envelope: {}, remaining: 9, chainHash: '', chainWarning }
    },
    signNodeEnvelope: async () => 'signature', signPoolEnvelope: async () => ({}),
    bindPoolSecretToSession: async () => ({}), loadBatches: async () => {}, loadPoolSummary: async () => {},
    describeError: error => error.message,
  }
  await handler('distribute', 'handleDistributeFromPool', context)()
  noChainToast(calls)
  assert.equal(context.submitting.value, false)
  if (apiFailure) assert.match(context.errorMessage.value, /资源不可用/)
  else {
    assert.equal(context.result.value.keyStored, true)
    assert.equal(context.result.value.chainHash, '', 'do not invent a chain receipt')
    assert.equal(calls.filter(call => call.type === 'success').length, 1)
  }
}

for (const name of ['handleApprove', 'handleReject']) {
  for (const apiFailure of [false, true]) {
    const { calls, ElMessage } = messages()
    let requestedDecision
    const context = {
      ElMessage, ElMessageBox: { confirm: async () => {}, prompt: async () => ({ value: 'reason' }) },
      load: async () => {}, loadPendingRequests: async () => {},
      decideAuthorizationRequest: async (_id, request) => {
        requestedDecision = request.decision
        if (apiFailure) throw Error('权限不足')
        return { chainWarning, chainHash: '', granted: { created: [1, 2], reactivated: [] } }
      }
    }
    await handler('nodeauth', name, context)({ id: 1, requesterNodeCode: 'A', targetNodeCode: 'B' })
    assert.equal(requestedDecision, name === 'handleApprove' ? 'approve' : 'reject')
    noChainToast(calls)
    assert.equal(calls[0].type, apiFailure ? 'error' : 'success')
    if (apiFailure) assert.match(calls[0].text, /权限不足/)
  }
}

for (const chainHash of ['', 'verified-transaction']) {
  for (const apiFailure of [false, true]) {
    const { calls, ElMessage } = messages()
    const context = {
      technicalFlow: ref(null), updating: ref(''), node: ref({ nodeId: 'A' }), lastRotate: ref(null),
      selfTestResults: ref({}), variantOf: () => 768, formatGenerationName: () => 'Kyber',
      RECONCILE: { MATCH: 'MATCH' }, ElMessage, describeError: error => error.message,
      cards: ref([{ algorithm: 'KYBER', active: { keyId: 'original', keyVersion: 2 }, reconcile: { state: 'MATCH' } }]),
      load: async () => {},
      generateAndRegisterNodeKey: async () => {
        if (apiFailure) throw Error('密钥登记失败')
        return { material: { keyRef: 'ref', keyId: 'original', version: 2 },
          result: { keyId: 'original', keyVersion: 2, chainHash, chainWarning }, check: { ok: true } }
      }
    }
    await handler('keyupdate', 'handleRotate', context)({ algorithm: 'KYBER', label: 'Kyber', active: { keyId: 'original', keyVersion: 1 } })
    noChainToast(calls)
    assert.equal(calls[0].type, apiFailure ? 'error' : 'success')
    assert.equal(context.updating.value, '')
    if (apiFailure) assert.match(calls[0].text, /密钥登记失败/)
    else assert.equal(context.lastRotate.value.chainHash, chainHash, 'preserve the actual chain state')
  }
}

// Audit every shipped frontend source file, including modules not exercised above.
let checked = 0
const violations = []
function walk(node, visit) {
  if (!node || typeof node !== 'object') return
  if (node.type) visit(node)
  for (const [key, value] of Object.entries(node)) {
    if (key === 'loc') continue
    if (Array.isArray(value)) value.forEach(child => walk(child, visit))
    else if (value && typeof value === 'object') walk(value, visit)
  }
}
function audit(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name)
    if (entry.isDirectory()) { audit(file); continue }
    if (!/\.(vue|js|ts)$/.test(file)) continue
    const raw = readFileSync(file, 'utf8')
    const descriptor = file.endsWith('.vue') ? parse(raw).descriptor : null
    const scripts = descriptor ? [descriptor.script?.content, descriptor.scriptSetup?.content].filter(Boolean) : [raw]
    for (const source of scripts) {
      const ast = babelParse(source, { sourceType: 'module', plugins: ['typescript'] })
      checked++
      walk(ast, node => {
        if (node.type !== 'CallExpression') return
        const callee = source.slice(node.callee.start, node.callee.end)
        if (!/(?:ElMessage|ElNotification|ElMessageBox|\$modal|\$message|\$notify)/.test(callee)) return
        if (!/(?:warning|warn|error|alert|notify|msgSuccess|msgWarning|msgError|msgInfo|success|ElMessage|ElNotification)$/.test(callee)) return
        const argumentsText = node.arguments.map(argument => source.slice(argument.start, argument.end)).join(' ')
        if (/chainWarning|chain_warning|链(?:不可用|未配置)|存证未成功/.test(argumentsText)) violations.push(file)
      })
    }
  }
}
audit(join(frontend, 'src'))
audit(join(frontend, '../../kms-acceptance/front/src'))
assert.deepEqual(violations, [], 'non-blocking chain warnings must not produce popup messages')
console.log(`PASS: ${checked} frontend scripts audited; consume/approve/reject/update success has no chain popup, real failures remain visible, chain receipts unchanged`)
