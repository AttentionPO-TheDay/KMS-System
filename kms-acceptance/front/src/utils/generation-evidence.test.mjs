import test from 'node:test'
import assert from 'node:assert/strict'
import { performanceOutcome, measuredPerformance } from './test-results.js'
import { performanceCalculation } from './evidence-presentation.js'

test('successful HTTP response throughput is the generation metric', () => {
  const run = { scenarioId: 'generate-tps', status: 'passed', passedTps: true, summary: { totalRequests: 120000, non2xxResponses: 0, successfulRequestsPerSec: 120000 }, wrkCommand: ['wrk','-d','1s'] }
  assert.equal(performanceOutcome(run).state, 'passed')
  assert.equal(measuredPerformance(run), 120000)
  assert.equal(performanceCalculation(run).value, 120000)
})

test('generation formula subtracts non-success responses', () => {
  const run = { scenarioId: 'generate-tps', status: 'failed_threshold', passedTps: false, summary: { totalRequests: 6000, non2xxResponses: 2, successfulRequestsPerSec: 5998 }, wrkCommand: ['wrk','-d','1s'] }
  assert.equal(performanceCalculation(run).value, 5998)
  assert.equal(measuredPerformance(run), 5998)
})
