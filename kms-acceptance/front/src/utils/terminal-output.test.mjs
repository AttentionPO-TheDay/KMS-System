import test from 'node:test'
import assert from 'node:assert/strict'
import { logTime, terminalLines, terminalText } from './terminal-output.js'
import { securityExecution } from './execution-trace.js'

test('terminal renders observations and field values without invented timing or success', () => {
  const rows = terminalLines([{ id: 'a', from: '执行器', to: '数据库', action: '核验', output: '未完成', state: 'failed', fields: [['count', 0], ['verified', false], ['missing', undefined]] }])
  assert.equal(rows[0].time, '--:--:--.---')
  assert.equal(rows.at(-1).tag, 'FAIL')
  const text = terminalText(rows)
  assert.match(text, /count=0/)
  assert.match(text, /verified=false/)
  assert(!text.includes('elapsed='))
  assert(!text.includes('missing='))
  assert.equal(logTime('invalid'), '--:--:--.---')
})

test('actual executor steps interleave with requests using nanosecond order', () => {
  const rows = securityExecution({ reasonMatched: true, requests: [{ name: '发送非法请求并核对拒绝原因', url: '/attack', method: 'POST', statusCode: 403, durationMs: 0, recordedAt: '2026-10-22T12:00:00.123000001Z' }], probeSteps: [
    { kind: 'BUILD', name: '构造请求', detail: 'JSON', state: 'info', recordedAt: '2026-10-22T12:00:00.122999999Z' },
    { kind: 'ASSERT', name: '校验结果', detail: 'matched', state: 'success', recordedAt: '2026-10-22T12:00:00.123000002Z' }
  ] })
  assert.deepEqual(rows.map(row => row.id), ['probe-0', 'attack-0', 'probe-1'])
  assert.equal(terminalLines(rows)[0].tag, 'BUILD')
  assert.equal(terminalLines(rows).at(-1).tag, 'OK')
})

test('thread log reports recorded task intervals and drops invalid spans', () => {
  const rows = terminalLines([], [{ worker: 'worker-1', startMs: 1, endMs: 10 }, { worker: 'bad', startMs: 10, endMs: 1 }])
  assert.equal(rows.length, 1)
  assert.equal(rows[0].tag, 'THREAD')
  assert.match(rows[0].text, /elapsed=9 ms/)
})

test('process sampling logs retain the process identity instead of claiming threads', () => {
  const rows = terminalLines([], [{ worker: 'process-812', kind: 'process', startMs: 1, endMs: 12 }])
  assert.equal(rows[0].tag, 'PROCESS')
  assert.match(rows[0].text, /process-812/)
})

test('different model output fields produce model-specific terminal records', () => {
  const row = { variant: 512, n: 512, m: 512, q: 3329, beta: 406, log2Rop: 108, durationMs: 2, rawCost: 'red: 2^107\nsvp: 2^106\nη: 404\nd: 1021\nmem: 2^90\nm: 512\n↻: 3' }
  const text = model => terminalText(terminalLines(securityExecution({ quantumEvidence: { model, estimates: [row] } })))
  assert.match(text('primal_bdd'), /后续求解成本/)
  assert(!text('primal_usvp').includes('后续求解成本'))
  assert.match(text('dual'), /内存规模/)
  assert(!text('primal_bdd').includes('内存规模'))
  assert.notEqual(text('primal_usvp').split('\n').length, text('primal_bdd').split('\n').length)
})
