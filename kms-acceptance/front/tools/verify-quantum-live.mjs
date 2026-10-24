// Execute the deployed workbench's three models in an isolated administrator session.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const origin = process.env.KMS_DEMO_ORIGIN || 'https://10.112.125.22:8443'
const output = process.env.KMS_EVIDENCE_DIR || mkdtempSync(join(tmpdir(), 'kms-quantum-live-'))
mkdirSync(output, { recursive: true })
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const browser = spawn(chrome, ['--headless=new', '--no-first-run', '--remote-debugging-port=9441',
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-quantum-browser-'))}`, '--window-size=1440,1100', 'about:blank'],
  { stdio: 'ignore', windowsHide: true })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let socket, seq = 0
const pending = new Map(), errors = []
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => { pending.delete(id); reject(Error(method)) }, 20000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const data = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!data.exceptionDetails, JSON.stringify(data.exceptionDetails))
  return data.result?.value
}
async function waitFor(expression, attempts = 600) {
  for (let i = 0; i < attempts; i++) { if (await evaluate(expression)) return; await delay(250) }
  throw Error('Timed out: '+expression)
}
async function shot(name) {
  const data = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync(join(output, name), Buffer.from(data.data, 'base64'))
}
try {
  let target
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9441/json/list')).json()).find(r => r.type === 'page') } catch {}
    if (!target) await delay(100)
  }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const data = JSON.parse(event.data)
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text)
    const request = pending.get(data.id)
    if (request) {
      pending.delete(data.id); clearTimeout(request.timer)
      data.error ? request.reject(Error(JSON.stringify(data.error))) : request.resolve(data.result)
    }
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Page.navigate', { url: origin+'/acceptance/#/load-test' })
  await waitFor(`location.origin===${JSON.stringify(origin)}&&document.readyState==='complete'`)
  await evaluate(`(async()=>{const initial=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const response=await fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',headers:{'Content-Type':'application/json',
    'X-Kms-Demo-Revision':String(initial.revision),'X-Kms-Demo-CSRF':initial.csrfToken},body:'{}'});
    const b=await response.json(); if(!response.ok||b.code!==200)throw Error('Administrator session failed')})()`)
  await rpc('Page.reload', { ignoreCache: true })
  await waitFor(`document.querySelector('[data-criterion-id="quantum-attacks"] button:not(:disabled)')`)
  assert(await evaluate(`document.querySelector('[data-criterion-id="symmetric-reclaim"]')!==null`))
  assert.equal(await evaluate(`document.querySelector('[data-criterion-id="pq-protocol-validation"] select').options.length`), 5)
  assert.equal(await evaluate(`document.querySelector('[data-criterion-id="quantum-attacks"] select').options.length`), 4)
  await evaluate(`document.querySelector('[data-criterion-id="quantum-attacks"] .btn-primary').click()`)
  await waitFor(`document.querySelectorAll('[data-criterion-id="quantum-attacks"] .security-result.evaluated').length===3`)
  const results = await evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const r=await(await fetch('/acceptance-api/security/runs',{headers:{'X-Kms-Demo-Revision':String(c.revision)}})).json();
    return r.data.filter(x=>x.caseId.startsWith('quantum-lwe-'))})()`)
  assert.equal(results.length, 3)
  const models = { 'quantum-lwe-usvp': 'primal_usvp', 'quantum-lwe-bdd': 'primal_bdd', 'quantum-lwe-dual': 'dual' }
  for (const r of results) {
    assert.equal(r.status, 'completed', r.error)
    assert.equal(r.verdict, 'evaluated'); assert.equal(r.passed, false)
    assert.equal(r.legalControlPassed, true); assert.equal(r.evidenceVersion, 4)
    const e = r.quantumEvidence
    assert.equal(e.model, models[r.caseId]); assert.equal(e.evaluationComplete, true)
    assert.equal(e.acceptancePassed, false); assert.equal(e.circuit.verified, true)
    assert.equal(e.circuit.target, e.circuit.recovered)
    assert.equal(e.estimatorCommit, 'e4333d9bf9ef42fd8a29651b0c559fba7ce0d834')
    assert.deepEqual(e.estimates.map(row => row.variant), [512, 768, 1024])
    assert(e.estimates.every(row => Number.isFinite(row.log2Rop) && row.log2Rop > 0))
    assert(r.requests.some(row => row.url === '/evaluate' && row.statusCode === 200))
    writeFileSync(join(output, r.caseId+'.json'), JSON.stringify(r, null, 2))
  }
  assert(await evaluate(`document.querySelector('[data-criterion-id="quantum-attacks"] .item-status').innerText==='评估完成，指标待核验'`))
  assert.equal(await evaluate(`document.querySelectorAll('.quantum-evidence tbody tr').length`), 9)
  await evaluate(`document.querySelector('[data-criterion-id="quantum-attacks"]').scrollIntoView({block:'start'})`)
  await shot('quantum-desktop.png')
  await evaluate(`document.querySelector('[data-criterion-id="quantum-attacks"] .quantum-evidence details').open=true`)
  await shot('quantum-circuit.png')
  for (const width of [768, 390]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width === 390 })
    await delay(200)
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'overflow '+width)
    await shot('quantum-'+width+'.png')
  }
  assert.deepEqual(errors, [])
  const summary = { origin, verified: true, runs: results.map(r => ({ id: r.id, caseId: r.caseId, status: r.status,
    verdict: r.verdict, legalControlPassed: r.legalControlPassed,
    log2Rop: r.quantumEvidence.estimates.map(e => e.log2Rop) })), displayedParameterRows: 9, responsiveWidths: [1440, 768, 390] }
  writeFileSync(join(output, 'verification.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify(summary))
} catch (error) {
  if (socket?.readyState === 1) {
    console.log(await evaluate('document.body.innerText.slice(0,2200)'))
    await shot('failure.png')
  }
  throw error
} finally {
  socket?.close(); browser.kill()
  for (const r of pending.values()) clearTimeout(r.timer)
}
