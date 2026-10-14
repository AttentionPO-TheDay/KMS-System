import test from 'node:test'
import assert from 'node:assert/strict'
import { demoState, canRunAcceptance, refreshDemoContext, acceptanceFetch } from './demo-context.js'
import { API } from './index.js'

function reset() {
  Object.assign(demoState, { context: null, available: false, stale: false, busy: false, message: '' })
}
function context(principalType = 'ADMIN', revision = 1) {
  return { code: 200, data: { enabled: true, entryMode: 'DEMO', principalType, revision, csrfToken: 'csrf' } }
}
function response(body, status = 200) { return { ok: status < 400, status, json: async () => body } }

test('same-origin bootstrap and mutations carry only revision and CSRF', async () => {
  reset()
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return response(url.includes('/context') ? context() : { id: 'run-fixture', status: 'running' }, url.includes('/context') ? 200 : 202)
  }
  const run = await acceptanceFetch('/runs', { method: 'POST', body: '{"scenarioId":"demo-boundary-probe"}', headers: { 'X-Internal-Token': 'spoof', Authorization: 'Bearer fake' } })
  assert.equal(run.status, 'running')
  assert.equal(calls[0].url, '/demo-api/lifecycle/demo/context')
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.equal(calls[1].url, '/acceptance-api/runs')
  assert.equal(calls[1].options.credentials, 'same-origin')
  assert.deepEqual(calls[1].options.headers, { 'Content-Type': 'application/json', 'X-Kms-Demo-Revision': '1', 'X-Kms-Demo-CSRF': 'csrf' })
  assert.equal(demoState.busy, true)
  assert.equal(canRunAcceptance.value, false)
  await assert.rejects(acceptanceFetch('/runs', { method: 'POST', body: '{}' }), /正在执行/)
  globalThis.fetch = async () => response({ data: [] })
  await acceptanceFetch('/runs')
  assert.equal(demoState.busy, false)
})

test('non-admin and unavailable contexts disable all dispatch', async () => {
  reset()
  globalThis.fetch = async () => response(context('NODE'))
  await refreshDemoContext()
  assert.equal(canRunAcceptance.value, false)
  await assert.rejects(acceptanceFetch('/health'), /管理员/)
  reset()
  globalThis.fetch = async () => { throw new Error('authority unavailable') }
  await assert.rejects(refreshDemoContext(), /unavailable/)
  assert.equal(demoState.available, false)
  assert.equal(canRunAcceptance.value, false)
})

test('context revision change never silently adopts a new role or replays', async () => {
  reset()
  globalThis.fetch = async () => response(context())
  await refreshDemoContext()
  globalThis.fetch = async () => response(context('NODE', 2))
  await refreshDemoContext()
  assert.equal(demoState.stale, true)
  assert.equal(demoState.context.revision, 1)
  assert.equal(demoState.context.principalType, 'ADMIN')
  await assert.rejects(acceptanceFetch('/runs'), /身份已改变/)
})

test('integrated API returns decoded data and failed cancellation preserves busy state', async () => {
  reset()
  globalThis.fetch = async url => response(url.includes('/context') ? context() : { status: 'ok', data: [] })
  const health = await API.getHealth()
  assert.equal(health.status, 'ok')
  assert.deepEqual((await API.getAcceptanceCriteria()).data, [])
  demoState.busy = true
  globalThis.fetch = async () => response({ message: 'authority unavailable' }, 503)
  await assert.rejects(API.cancelRun('run-fixture'), /unavailable/)
  assert.equal(demoState.busy, true)
})

test('stale response and malformed routes fail closed', async () => {
  reset()
  globalThis.fetch = async () => response(context())
  await refreshDemoContext()
  globalThis.fetch = async () => response({ message: 'DEMO_REVISION_STALE' }, 409)
  await assert.rejects(acceptanceFetch('/health'), /STALE/)
  assert.equal(demoState.stale, true)
  for (const path of ['https://evil.example/runs', '/runs/../health', '/runs?target=evil', '/internal/generate']) {
    await assert.rejects(acceptanceFetch(path), /未开放/)
  }
})
