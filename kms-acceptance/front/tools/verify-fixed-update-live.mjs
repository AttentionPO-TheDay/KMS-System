// Executes one real update run on existing acceptance keys; never generates keys.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const origin = process.env.KMS_DEMO_ORIGIN || 'http://127.0.0.1:8088'
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const output = mkdtempSync(join(tmpdir(), 'kms-fixed-update-live-'))
const profile = mkdtempSync(join(tmpdir(), 'kms-fixed-update-browser-'))
const browser = spawn(chrome, ['--headless=new', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--window-size=1440,1100', 'about:blank'], { stdio: 'ignore', windowsHide: true })
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
  for (let i = 0; i < 600; i++) { if (await evaluate(expression)) return; await delay(200) }
  throw Error(`Timed out: ${expression}`)
}
async function shot(name) {
  const data = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync(join(output, name), Buffer.from(data.data, 'base64'))
}
try {
  let target
  for (let i = 0; i < 80 && !target; i++) {
    try {
      const port = readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]
      target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(row => row.type === 'page')
    } catch {}
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
    const initial=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const response=await fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',headers:{'Content-Type':'application/json','X-Kms-Demo-Revision':String(initial.revision),'X-Kms-Demo-CSRF':initial.csrfToken},body:'{}'});
    if(!response.ok)throw Error('Administrator session failed');
  })()`)
  await rpc('Page.reload', { ignoreCache: true })
  await waitFor(`document.querySelector('[data-criterion-id="key-update"] button:not(:disabled)')`)
  await evaluate(`document.querySelector('[data-criterion-id="key-update"] button').click()`)
  await waitFor(`document.querySelector('[data-criterion-id="key-update"] .fixed-update-evidence') || document.querySelector('[data-criterion-id="key-update"] .result-error')`)
  const result = await evaluate(`(async()=>{const ctx=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;return (await(await fetch('/acceptance-api/runs',{headers:{'X-Kms-Demo-Revision':String(ctx.revision)}})).json()).data.find(row=>row.scenarioId==='update-tps')})()`)
  writeFileSync(join(output, 'run.json'), JSON.stringify(result, null, 2))
  assert(!result.error, result.error)
  const e = result.fixedUpdateEvidence
  assert.equal(e.version, 2); assert.equal(e.selected, 6000); assert.equal(e.submitted, 6000)
  assert.equal(e.completed, 6000); assert.equal(e.verified, true)
  assert.equal(result.metricCheck.collected, true)
  assert.equal(result.summary.successfulRequestsPerSec, e.completed * 1000 / e.elapsedMs)
  assert.equal(result.passedTps, result.summary.successfulRequestsPerSec >= 5000)
  assert.equal(result.status, result.passedTps ? 'passed' : 'failed_threshold')
  await shot('fixed-update-desktop.png')
  for (const width of [768, 390]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width === 390 })
    await delay(150)
    assert(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), `overflow at ${width}`)
    await shot(`fixed-update-${width}.png`)
  }
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await rpc('Page.navigate', { url: origin + '/acceptance/#/lifecycle' })
  await waitFor(`document.body.innerText.includes(${JSON.stringify(result.id)})`)
  await evaluate(`[...document.querySelectorAll('tbody tr')].find(row=>row.innerText.includes(${JSON.stringify(result.id)})).querySelector('button').click()`)
  await waitFor(`document.querySelector('.details-panel tbody tr')`)
  assert(await evaluate(`[...document.querySelectorAll('.details-panel tbody tr')].every(row=>{const values=row.children[3].innerText.split('→').map(Number);return values[1]>values[0]})`))
  await shot('fixed-update-versions.png')
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ id: result.id, status: result.status, selected: e.selected, submitted: e.submitted, accepted: e.accepted, updated: e.completed, elapsedMs: e.elapsedMs, actualTPS: result.summary.successfulRequestsPerSec, acceptedTPS: e.acceptedTps, output }))
} catch (error) {
  if (socket?.readyState === 1) { await shot('failure.png'); console.log(await evaluate('document.body.innerText.slice(0,1600)')) }
  console.error('Browser evidence:', output)
  throw error
} finally {
  socket?.close(); browser.kill()
}
