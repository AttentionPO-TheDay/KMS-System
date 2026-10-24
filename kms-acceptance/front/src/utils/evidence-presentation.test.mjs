import test from 'node:test'
import assert from 'node:assert/strict'
import { securityRequestGroups, parseCostFields, performanceCalculation, performanceMethod } from './evidence-presentation.js'
import { quantumModels } from '../config/quantumModels.js'

const trace = (name, url, statusCode = 200, message = 'businessCode=200') => ({ name, url, statusCode, outcome: 'received', message })

test('an attack against a session endpoint remains core evidence regardless of its position', () => {
  const attack = trace('发送非法请求并核对拒绝原因', '/demo-api/lifecycle/demo/context/admin', 403)
  const groups = securityRequestGroups({ requests: [
    trace('建立独立测试会话', '/demo-api/lifecycle/demo/context'),
    trace('进入测试节点 A', '/demo-api/lifecycle/demo/context/entry'),
    trace('攻击前验证合法节点读取', '/demo-api/pqkds/node-self/'),
    attack,
    trace('攻击后复查合法节点读取', '/demo-api/pqkds/node-self/')
  ] })
  assert.deepEqual(groups.core, [attack])
  assert.equal(groups.preparation.length, 2)
  assert.equal(groups.controls.length, 2)
})

test('failed setup, failed legal controls and unknown steps never disappear into successful preparation', () => {
  const requests = [
    trace('进入测试节点 A', '/entry', 503),
    trace('攻击前验证合法节点读取', '/node-self', 403),
    trace('建立独立测试会话', '/context', 200, 'businessCode=400 errorCode=INVALID'),
    trace('未识别的步骤', '/new-endpoint'),
    { name: '建立独立测试会话', url: '/context', outcome: 'error' }
  ]
  assert.deepEqual(securityRequestGroups({ requests }).core, requests)
})

test('cleanup is distinguished by endpoint even when the last attack stage name is reused', () => {
  const groups = securityRequestGroups({ requests: [trace('攻击后复查合法节点读取', '/demo-api/lifecycle/demo/context/logout')] })
  assert.equal(groups.cleanup.length, 1)
  assert.equal(groups.controls.length, 0)
})

test('cost fields retain reported values and each model exposes its own parameters', () => {
  const values = parseCostFields(' red: ≈2^107.6\n svp: ≈2^107.3\n η: 404\n d: 1021\n tag: bdd')
  assert.equal(values.svp, '≈2^107.3')
  assert.equal(values.η, '404')
  assert.deepEqual(parseCostFields(null), {})
  assert.equal(quantumModels.primal_bdd.method, 'LWE.primal_bdd')
  assert(quantumModels.primal_bdd.fields.includes('svp'))
  assert(quantumModels.dual.fields.includes('mem'))
  assert(!quantumModels.primal_usvp.fields.includes('mem'))
  assert.equal(new Set(Object.values(quantumModels).map(model => JSON.stringify(model.steps))).size, 3)
})

test('update calculation uses verified completion rather than accepted requests', () => {
  const run = { scenarioId: 'update-tps', fixedUpdateEvidence: { accepted: 6000, completed: 3500, verified: true, elapsedMs: 1000 } }
  assert.equal(performanceCalculation(run).value, 3500)
  run.fixedUpdateEvidence.verified = false
  assert.equal(performanceCalculation(run).value, null)
})

test('recovery percentage uses attempts independently of elapsed time and injected samples', () => {
  const run = { scenarioId: 'revoke-rate', abnormalEvidence: { injected: 6000, attempted: 4000, revoked: 3500, elapsedMs: 100 } }
  assert.equal(performanceCalculation(run).value, 87.5)
  run.scenarioId = 'revoke-tps'
  assert.equal(performanceCalculation(run).value, 35000)
})

test('zero, missing and invalid measurements remain distinct in displayed formulas', () => {
  assert.equal(performanceCalculation({ symmetricEvidence: { reclaimed: 0, elapsedMs: 100 } }).value, 0)
  assert.equal(performanceCalculation({ symmetricEvidence: { elapsedMs: 100 } }).value, null)
  assert.equal(performanceCalculation({ symmetricEvidence: { reclaimed: 100, elapsedMs: 0 } }).value, null)
  assert.equal(performanceCalculation({ symmetricEvidence: { reclaimed: 100, elapsedMs: Infinity } }).value, null)
  assert.equal(performanceCalculation({ scenarioId: 'revoke-rate', abnormalEvidence: { attempted: 4000 } }).value, null)
  assert.equal(performanceCalculation({ scenarioId: 'revoke-rate', abnormalEvidence: { revoked: 0, attempted: 0 } }).value, null)
})

test('generation reports HTTP throughput using the recorded duration without counting socket errors twice', () => {
  const run = { scenarioId: 'generate-tps', wrkCommand: ['wrk', '-d', '2s'], summary: { totalRequests: 100, non2xxResponses: 10, socketErrors: 5 } }
  assert.equal(performanceCalculation(run, { durationSeconds: 5 }).value, 45)
  assert.match(performanceCalculation(run).formula, /HTTP/)
  assert.equal(performanceCalculation({ scenarioId: 'generate-tps', summary: {} }).value, null)
})

test('generation retains the recorded measurement window after command redaction', () => {
  const run = { scenarioId: 'generate-tps', wrkCommand: null, summary: { totalRequests: 106660, non2xxResponses: 0, rawOutput: 'Running 1s test @ http://generate-go:8081/generate/request/ENROLL_KEY\n  2 threads and 340 connections' } }
  assert.equal(performanceCalculation(run, { durationSeconds: 5 }).value, 106660)
  assert.match(performanceCalculation(run).substitution, /÷ 1$/)
})

test('performance scenarios have separate methods and measurement scopes', () => {
  const methods = ['generate-tps', 'update-tps', 'revoke-tps', 'revoke-rate', 'symmetric-reclaim-tps'].map(scenarioId => performanceMethod({ scenarioId }))
  assert(methods.every(method => method.steps.length === 3 && method.scope))
  assert.equal(new Set(methods.map(method => method.title)).size, 5)
})
