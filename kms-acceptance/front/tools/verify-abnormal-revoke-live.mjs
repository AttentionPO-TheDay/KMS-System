// Real local deployment: own Demo session; only the isolated anomaly fixture runs.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const origin = process.env.KMS_DEMO_ORIGIN || 'http://127.0.0.1:8088'
const scenarioId = process.env.KMS_ABNORMAL_SCENARIO || 'revoke-tps'
assert(['revoke-tps', 'revoke-rate'].includes(scenarioId))
const recoveryRate = scenarioId === 'revoke-rate'
const criterionId = recoveryRate ? 'revoke-rate' : 'abnormal-revoke'
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const output = mkdtempSync(join(tmpdir(), 'kms-abnormal-live-'))
const profile = mkdtempSync(join(tmpdir(), 'kms-abnormal-browser-'))
const browser = spawn(chrome, ['--headless=new', '--no-first-run', '--remote-debugging-port=9423',
  `--user-data-dir=${profile}`, '--window-size=1440,1100', 'about:blank'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let socket, seq = 0
const pending = new Map(), errors = []
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => reject(Error(method)), 15000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const data = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!data.exceptionDetails, JSON.stringify(data.exceptionDetails))
  return data.result?.value
}
async function waitFor(expression) {
  for (let i = 0; i < 200; i++) { if (await evaluate(expression)) return; await delay(200) }
  throw Error(`Timed out: ${expression}\n${await evaluate('document.body.innerText.slice(0,1600)')}`)
}
async function shot(name) {
  const data = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync(join(output, name), Buffer.from(data.data, 'base64'))
}
try {
  let target
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9423/json/list')).json()).find(row => row.type === 'page') } catch {}
    if (!target) await delay(100)
  }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const data = JSON.parse(event.data)
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text)
    const request = pending.get(data.id)
    if (request) { pending.delete(data.id); clearTimeout(request.timer); data.error ? request.reject(Error(JSON.stringify(data.error))) : request.resolve(data.result) }
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Page.navigate', { url: origin + '/acceptance/#/load-test' })
  await waitFor(`location.origin === ${JSON.stringify(origin)} && document.readyState === 'complete'`)
  await evaluate(`(async () => {
    const initial = await (await fetch('/demo-api/lifecycle/demo/context')).json();
    const response = await fetch('/demo-api/lifecycle/demo/context/admin', { method:'POST',
      headers:{'Content-Type':'application/json','X-Kms-Demo-Revision':String(initial.data.revision),'X-Kms-Demo-CSRF':initial.data.csrfToken},body:'{}'});
    if(!response.ok)throw Error('Administrator session failed');
  })()`)
  await rpc('Page.reload', { ignoreCache: true })
  await waitFor(`document.querySelector('[data-criterion-id="${criterionId}"] button:not(:disabled)')`)
  await evaluate(`document.querySelector('[data-criterion-id="${criterionId}"] button').click()`)
  await waitFor(`document.querySelector('[data-criterion-id="${criterionId}"] .performance-result table')`)
  const result = await evaluate(`(async () => {
    const context=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const runs=await(await fetch('/acceptance-api/runs',{headers:{'X-Kms-Demo-Revision':String(context.revision)}})).json();
    return runs.data.find(row=>row.scenarioId===${JSON.stringify(scenarioId)});
  })()`)
  const measuredPercentage = result.abnormalEvidence.revoked * 100 / (recoveryRate ? result.abnormalEvidence.attempted : result.abnormalEvidence.injected)
  const meetsTarget = recoveryRate ? measuredPercentage >= 98 : result.summary.successfulRequestsPerSec >= result.targetTps
  assert.equal(result.passedTps, recoveryRate || meetsTarget)
  assert.equal(result.status, meetsTarget ? 'passed' : 'failed_threshold')
  assert.equal(result.metricCheck.passed, recoveryRate ? meetsTarget : true)
  assert.equal(result.metricCheck.value, measuredPercentage)
  assert.equal(result.metricCheck.target, recoveryRate ? 98 : 100)
  assert.equal(result.metricCheck.operator, '>=')
  assert.equal(result.abnormalEvidence.version, 2)
  assert.equal(result.abnormalEvidence.injected, 6000)
  assert.equal(result.abnormalEvidence.attempted, 6000)
  assert.deepEqual(result.abnormalEvidence.batches.map(batch => batch.attempted), [5000, 1000])
  assert(result.abnormalEvidence.detected >= result.abnormalEvidence.revoked)
  assert(result.abnormalEvidence.detected <= result.abnormalEvidence.injected)
  if (!recoveryRate) assert.equal(result.abnormalEvidence.revoked, 6000)
  assert.equal(result.abnormalEvidence.poolRevoked, result.abnormalEvidence.revoked)
  assert.equal(result.abnormalEvidence.sessionsRevoked, result.abnormalEvidence.revoked)
  assert.equal(result.abnormalEvidence.invalidations, result.abnormalEvidence.revoked)
  assert.equal(result.abnormalEvidence.controlsPassed, 4)
  assert.equal(result.abnormalEvidence.cleanupComplete, true)
  if (recoveryRate) assert(await evaluate(`document.querySelector('[data-criterion-id="revoke-rate"]').innerText.includes('>= 98') && document.querySelector('[data-criterion-id="revoke-rate"]').innerText.includes('实际发起回收密钥数')`))
  await shot('abnormal-desktop.png')
  for (const width of [768, 390]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width === 390 })
    await delay(150)
    assert(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), `overflow at ${width}`)
    await shot(`abnormal-${width}.png`)
  }
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await rpc('Page.navigate', { url: origin + '/acceptance/#/lifecycle' })
  await waitFor(`document.querySelector('.audit-tabs button')`)
  await evaluate(`[...document.querySelectorAll('.audit-tabs button')].find(row=>row.innerText===${JSON.stringify(recoveryRate ? '异常密钥回收率' : '异常回收测试')}).click()`)
  await waitFor(`document.body.innerText.includes(${JSON.stringify(result.id)})`)
  await evaluate(`[...document.querySelectorAll('tbody tr')].find(row=>row.innerText.includes(${JSON.stringify(result.id)})).querySelector('button').click()`)
  await waitFor(`document.querySelector('.details-panel tbody tr')`)
  assert(await evaluate(`document.body.innerText.includes(${JSON.stringify(recoveryRate ? '实际发起回收' : '已注入异常样本')}) && document.body.innerText.includes('PUBLIC_KEY_MISSING')`))
  if (recoveryRate) assert(await evaluate(`document.body.innerText.includes('异常密钥回收率 ≥ 98%')`))
  await shot('abnormal-snapshots.png')
  await evaluate(`const filter=document.querySelector('.detail-filters select');filter.value='CONTROL_PASSED';filter.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('.detail-filters button').click()`)
  await waitFor(`document.querySelectorAll('.details-panel tbody tr').length===4 && document.body.innerText.includes('匹配 4 把')`)
  assert(await evaluate(`document.body.innerText.includes('MATERIALIZED_PUBLIC_KEY_MISMATCH')`))
  await shot('abnormal-controls.png')
  assert.deepEqual(errors, [])
  writeFileSync(join(output, 'run.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ scenarioId, status: result.status, measuredPercentage, injected: result.abnormalEvidence.injected,
    attempted: result.abnormalEvidence.attempted, batches: result.abnormalEvidence.batches.map(batch => ({ attempted: batch.attempted, revoked: batch.revoked })),
    revoked: result.abnormalEvidence.revoked, controls: result.abnormalEvidence.controlsPassed,
    elapsedMs: result.abnormalEvidence.elapsedMs, actualRate: result.summary.successfulRequestsPerSec,
    output, id: result.id }))
} catch (error) {
  if (socket?.readyState === 1) { console.log(await evaluate('document.body.innerText.slice(0,1800)')); await shot('failure.png') }
  throw error
} finally {
  socket?.close(); browser.kill()
}
