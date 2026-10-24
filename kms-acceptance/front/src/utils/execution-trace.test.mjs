import test from 'node:test'
import assert from 'node:assert/strict'
import { securityExecution, performanceExecution, latticeExecution, workerTimeline, preallocationExecution } from './execution-trace.js'

test('running requests produce no invented completion events or durations', () => {
  assert.deepEqual(securityExecution({ status: 'running', stage: '计算中' }), [])
  assert.deepEqual(performanceExecution({ status: 'running' }), [])
  for (const scenarioId of ['generate-tps', 'update-tps', 'revoke-tps', 'revoke-rate', 'symmetric-reclaim-tps']) {
    assert.deepEqual(performanceExecution({ scenarioId, status: 'running', summary: { totalRequests: 0, non2xxResponses: 0 } }), [], 'initial zero-valued summary is not an observed HTTP workload')
  }
  assert.deepEqual(latticeExecution(null), [])
  assert.deepEqual(securityExecution({ caseId: 'quantum-lwe-usvp', status: 'running', requests: [{ name: '发送非法请求并核对拒绝原因', url: '/protocol-control', statusCode: 400 }] }), [], 'quantum progress must not expose unrelated protocol control requests')
})

test('attack interaction uses rejection reason and legal control, omits common preparation', () => {
  const request = (name, url, statusCode = 200) => ({ name, url, method: 'POST', statusCode, durationMs: 0, recordedAt: '2026-10-22T12:00:00Z' })
  const run = { reasonMatched: false, actualReason: '另一种拒绝原因', legalControlPassed: true, requests: [
    request('建立独立测试会话', '/context'), request('发送非法请求并核对拒绝原因', '/node-self', 403), request('攻击后复查合法节点读取', '/node-self')
  ] }
  const rows = securityExecution(run)
  assert.equal(rows.length, 2)
  assert.equal(rows[0].state, 'failed')
  assert.equal(rows[0].durationMs, 0)
  assert.match(rows[0].output, /HTTP 403 · 传输层拒绝/)
  assert(rows[0].fields.some(([label, value]) => label === '业务状态' && value === '未记录'))
  assert.equal(rows[1].state, 'success')
  assert(!rows.some(row => /建立独立/.test(row.action)))
})

test('application validation distinguishes HTTP 200 from business rejection', () => {
  const rows = securityExecution({
    reasonMatched: true,
    actualReason: '签发仅支持规范 KYBER/FALCON 家族',
    expectedReason: '签发仅支持规范 KYBER/FALCON 家族',
    expectedCode: 'KEYGEN_SCHEME_INVALID',
    actualCode: 'KEYGEN_SCHEME_INVALID',
    testInput: 'algorithm=RSA-512',
    validationRule: '生成算法白名单',
    requests: [{ name: '发送非法请求并核对拒绝原因', url: '/keygen', method: 'POST', statusCode: 200,
      message: 'businessCode=409 errorCode=KEYGEN_SCHEME_INVALID reason=签发仅支持规范 KYBER/FALCON 家族', recordedAt: '2026-10-23T12:00:00Z' }]
  })
  assert.match(rows[0].output, /HTTP 200 · 业务拒绝 409/)
  assert(rows[0].fields.some(([label, value]) => label === '传输状态' && value === 'HTTP 200'))
  assert(rows[0].fields.some(([label, value]) => label === '业务状态' && value === '业务拒绝（409）'))
})

test('recorded before and after control checks appear once and preserve failures', () => {
  const before = { kind: 'CONTROL', name: '攻击前合法节点读取', state: 'success', detail: 'HTTP=200; actualNodeId=A', recordedAt: '2026-10-23T00:00:01Z' }
  const after = { kind: 'CONTROL', name: '攻击后合法节点读取', state: 'failed', detail: 'HTTP=200; actualNodeId=B; identityMatched=false', recordedAt: '2026-10-23T00:00:03Z' }
  const rows = securityExecution({ reasonMatched: true, probeSteps: [before, after], requests: [
    { name: '建立独立测试会话', url: '/context', statusCode: 200 },
    { name: '发送非法请求并核对拒绝原因', url: '/keygen', statusCode: 400, recordedAt: '2026-10-23T00:00:02Z' },
    { name: '攻击后复查合法节点读取', url: '/node-self', statusCode: 200, recordedAt: '2026-10-23T00:00:03Z' }
  ] })
  assert.equal(rows.length, 3)
  assert.equal(rows[0].action, before.name)
  assert.equal(rows[2].action, after.name)
  assert.equal(rows[2].state, 'failed')
  assert.match(rows[2].output, /identityMatched=false/)
  assert(!rows.some(row => row.id === 'legal-control'), 'do not repeat the after control or replace a failed identity check with HTTP success')
})

test('quantum trace reflects distinct estimator calls and recorded parameter costs only', () => {
  const row = { variant: 512, beta: 406, log2Rop: 108.46, durationMs: 11, n: 512, q: 3329, m: 512 }
  for (const model of ['primal_usvp', 'primal_bdd', 'dual']) {
    const rows = securityExecution({ quantumEvidence: { model, estimates: [row] } })
    assert.equal(rows.length, 1)
    assert.equal(rows[0].to, `LWE.${model}`)
    assert.equal(rows[0].durationMs, 11)
    assert(!rows[0].at, 'no inferred per-stage timestamps')
    assert(!rows[0].fields.some(([label]) => label === '计算含义'))
  }
})

test('update trace keeps submission and database completion separate', () => {
  const rows = performanceExecution({ fixedUpdateEvidence: { selected: 6000, submitted: 6000, accepted: 6000, completed: 3500, verified: false, submissionMs: 100, elapsedMs: 900 } })
  assert.match(rows[1].output, /6,000/)
  assert.match(rows[2].output, /3,500/)
  assert.equal(rows[2].state, 'failed')
  assert.equal(rows[2].durationMs, undefined, 'whole-run timing is not assigned to a substage')
})

test('revocation interactions expose failures and retain true measurement scope', () => {
  const rows = performanceExecution({ abnormalEvidence: { injected: 6000, detected: 6000, attempted: 4000, revoked: 3500, elapsedMs: 250, detectionElapsedMs: 25, detectionAt: '2026-10-21T16:00:00.100+08:00', revokeStartedAt: '2026-10-21T16:00:00.101+08:00', autoRevoked: true, rules: [], controls: 4, controlsPassed: 4, cleanupComplete: true } })
  assert.equal(rows[1].state, 'success')
  assert.equal(rows[2].state, 'failed')
  assert(rows[2].fields.some(([label, value]) => label === '实际失败' && value === '500'))
  assert(rows[2].fields.some(([label, value]) => label === '未发起' && value === '2,000'))
  assert.equal(rows[2].durationMs, undefined, 'do not infer a revoke duration from two different scopes')
  assert.equal(rows[3].state, 'success')
})

test('generation HTTP response cannot become a real key verification success', () => {
  const rows = performanceExecution({ scenarioId: 'generate-tps', status: 'passed', summary: { totalRequests: 10000, non2xxResponses: 0 } })
  assert.equal(rows[0].state, 'unknown')
  assert(rows[0].fields.some(([label, value]) => label === '观测范围' && value === '本轮接口成功响应统计'))
  assert.equal(rows.length, 1, 'HTTP statistics do not invent key verification events')
})

test('lattice evidence surfaces failed persistence and bound parent materials', () => {
  assert.equal(latticeExecution({ caseId: 'offline-trapdoor', kernelRelation: true, fullRank: true, secretPersistedEncrypted: false })[1].state, 'failed')
  const rows = latticeExecution({ caseId: 'basis-delegation', preparation: { parentId: 'root-1', id: 'child-1', nodeId: 'node-A' }, nodeBound: true, kernelRelation: true, preimageVerified: true, delegationMs: 12, reused: true })
  assert(rows[0].fields.some(([label, value]) => label === '主材料编号' && value === 'root-1'))
  assert(rows[0].fields.some(([, value]) => value === '复用已有记录'))
  assert.equal(rows[0].durationMs, 12)
})

test('thread timeline preserves actual overlap and discards malformed spans', () => {
  const result = workerTimeline([{ worker: 'b', startMs: 20, endMs: 50 }, { worker: 'a', startMs: 0, endMs: 40 }, { worker: 'a', startMs: 40, endMs: 100 }, { worker: 'bad', startMs: -1, endMs: 5 }, { worker: 'bad', startMs: 9, endMs: 5 }])
  assert.equal(result.durationMs, 100)
  assert.equal(result.rows.length, 2)
  assert.equal(result.rows[0].spans.length, 2)
  assert.equal(result.rows[1].spans[0].left, 20)
  assert.equal(result.rows[1].spans[0].width, 30)
  assert.deepEqual(workerTimeline(null).rows, [])
})

test('preallocation only shows observed local and server processing', () => {
  assert.deepEqual(preallocationExecution({}), [])
  const rows = preallocationExecution({ generated: 50, failed: 0, localMs: 20, serverMs: 30, verified: true, passed: true })
  assert.equal(rows.length, 2)
  assert.equal(rows[0].from, '发送节点本机')
  assert.equal(rows[1].durationMs, 30)
})
