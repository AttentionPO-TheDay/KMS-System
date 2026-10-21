import test from 'node:test'
import assert from 'node:assert/strict'
import { securityOutcome, securityProgress, performanceOutcome, measuredPerformance, algorithmCheckIds } from './test-results.js'

const pass = { status: 'completed', verdict: 'blocked', passed: true, evidenceVersion: 2, reasonMatched: true,
  legalControlPassed: true, expectedCode: 'INVALID_PARAMETER', actualCode: 'INVALID_PARAMETER',
  expectedReason: '生成参数集无效', actualReason: '生成参数集无效' }
test('same rejection code with absent or different reason never counts as a pass', () => {
  for (const changes of [{ evidenceVersion: undefined }, { reasonMatched: false }, { legalControlPassed: false },
    { actualReason: '公钥接口禁止上传私密生成材料' }, { actualReason: '' }, { actualCode: 'NOT_AUTHORIZED' }]) {
    assert.equal(securityOutcome({ ...pass, ...changes }).state, 'incomplete')
    assert.equal(securityProgress(['pq-test'], new Map([['pq-test', { ...pass, ...changes }]]), 1).thresholdMet, false)
  }
  assert.equal(securityOutcome({ ...pass, caseId: 'pq-test' }).label, '协议通过，算法待验')
})
test('one successful case stays visibly successful while the group is incomplete', () => {
  const result = securityProgress(['a', 'b', 'c', 'd'], new Map([['a', pass]]), 3)
  assert.equal(result.state, 'partial')
  assert.equal(result.passedCount, 1)
  assert.equal(result.pendingCount, 3)
  assert.equal(securityOutcome(pass).label, '防御成功')
})
test('four PQ protocol scenarios cannot certify quantum resistance or satisfy its attack-class metric', () => {
  const ids = ['pq-parameter-downgrade', 'pq-sign-encrypt-confusion', 'pq-secret-upload', 'pq-issuance-source-forgery']
  const result = securityProgress(ids, new Map(ids.map(caseId => [caseId, { ...pass, caseId }])), 3)
  assert.equal(result.passedCount, 0)
  assert.equal(result.thresholdMet, false)
  assert.equal(result.state, 'incomplete')
  assert.equal(result.statusLabel, '协议通过，算法待验')
})

const algorithmPass = caseId => ({ ...pass, caseId, evidenceVersion: 3, protocolPassed: true,
  algorithmEvidence: { version: 1, caseId, source: 'native', scope: 'functional', passed: true,
    checks: algorithmCheckIds[caseId].map(id => ({ id, passed: true, status: 'passed', expected: 'expected', actual: 'actual', recordedAt: '2026-10-19T00:00:00Z' })) } })
test('PQ passes only with all fixed real algorithm checks and protocol evidence', () => {
  const ids = Object.keys(algorithmCheckIds)
  const latest = new Map(ids.map(id => [id, algorithmPass(id)]))
  assert.equal(securityProgress(ids, latest, 3).statusLabel, '全部验证通过')
  assert.equal(securityProgress(ids, latest, 3).thresholdMet, true)
  const id = ids[0], original = latest.get(id)
  for (const change of [
    { protocolPassed: false }, { passed: false }, { evidenceVersion: 2 },
    { algorithmEvidence: { ...original.algorithmEvidence, checks: original.algorithmEvidence.checks.slice(1) } },
    { algorithmEvidence: { ...original.algorithmEvidence, checks: original.algorithmEvidence.checks.map(c => ({ ...c, passed: false })) } },
    { algorithmEvidence: { ...original.algorithmEvidence, caseId: ids[1] } }
  ]) {
    assert.notEqual(securityOutcome({ ...original, ...change }).state, 'passed')
  }
  latest.set(id, { ...original, passed: false, verdict: 'vulnerable' })
  assert.equal(securityProgress(ids, latest, 3).state, 'failed')
})
test('threshold and complete coverage remain separate; a failed extra case is visible', () => {
  const results = new Map(['a', 'b', 'c'].map(id => [id, pass]))
  let result = securityProgress(['a', 'b', 'c', 'd'], results, 3)
  assert.equal(result.thresholdMet, true)
  assert.equal(result.state, 'partial')
  results.set('d', { status: 'completed', verdict: 'vulnerable', passed: false })
  assert.equal(securityProgress(['a', 'b', 'c', 'd'], results, 3).state, 'failed')
  results.set('d', pass)
  assert.equal(securityProgress(['a', 'b', 'c', 'd'], results, 3).state, 'passed')
})
test('preparing, unavailable and cancelled runs cannot appear as defense failures or successes', () => {
  assert.equal(securityOutcome({ status: 'preparing', passed: false }).state, 'running')
  assert.equal(securityOutcome({ status: 'error', error: 'node unavailable' }).state, 'incomplete')
  assert.equal(securityOutcome({ status: 'cancelled' }).label, '已停止')
  assert.equal(securityOutcome({ status: 'completed', verdict: 'unknown', passed: true }).state, 'incomplete')
})
test('missing performance evidence is not shown as zero; measured zero remains visible', () => {
  assert.equal(measuredPerformance({ status: 'failed', summary: { totalRequests: 0 } }), null)
  assert.equal(measuredPerformance({ status: 'failed', summary: { totalRequests: 10, successfulRequestsPerSec: 0 } }), 0)
  assert.equal(measuredPerformance({ status: 'passed', scenarioId: 'revoke-rate', metricCheck: { collected: false, value: 100 } }), null)
  assert.equal(measuredPerformance({ status: 'passed', scenarioId: 'revoke-rate', metricCheck: { collected: true, value: 99 } }), 99)
  assert.equal(performanceOutcome({ status: 'error', error: 'pool unavailable' }).state, 'incomplete')
  assert.equal(performanceOutcome({ status: 'passed', passedTps: true, scenarioId: 'revoke-rate', metricCheck: { collected: false, passed: true } }).state, 'incomplete')
})
