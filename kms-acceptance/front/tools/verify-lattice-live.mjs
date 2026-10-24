import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const origin = process.env.KMS_DEMO_ORIGIN || 'https://10.112.125.22:8443'
const output = resolve(process.env.KMS_EVIDENCE_DIR || '../../output/lattice-verification/browser')
mkdirSync(output, { recursive: true })
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const browser = spawn(chrome, ['--headless=new', '--no-first-run', '--remote-debugging-port=9444',
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-lattice-browser-'))}`, '--window-size=1440,1100', 'about:blank'],
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
async function waitFor(expression, attempts = 240) {
  for (let i = 0; i < attempts; i++) { if (await evaluate(expression)) return; await delay(250) }
  throw Error('Timed out: ' + expression)
}
async function shot(name) {
  const data = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync(join(output, name), Buffer.from(data.data, 'base64'))
}
async function catalog() {
  return evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const r=await fetch('/acceptance-api/lattice',{headers:{'X-Kms-Demo-Revision':String(c.revision)}});
    if(!r.ok)throw Error('Read failed '+r.status);return(await r.json()).data})()`)
}
try {
  let target
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9444/json/list')).json()).find(r => r.type === 'page') } catch {}
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
  await rpc('Security.setIgnoreCertificateErrors', { ignore: true })
  await rpc('Page.navigate', { url: origin + '/acceptance/#/load-test' })
  await waitFor(`location.origin===${JSON.stringify(origin)}&&document.readyState==='complete'`)
  await evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const r=await fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',headers:{'Content-Type':'application/json',
    'X-Kms-Demo-Revision':String(c.revision),'X-Kms-Demo-CSRF':c.csrfToken},body:'{}'});
    if(!r.ok||(await r.json()).code!==200)throw Error('Admin session failed')})()`)
  await rpc('Page.reload', { ignoreCache: true })
  await waitFor(`document.querySelectorAll('.lattice-entry nav a').length===3`)
  const cases = ['offline-trapdoor', 'basis-delegation', 'parallel-sampling']
  const results = []
  let generatedRoot, delegated
  for (const id of cases) {
    await evaluate(`location.hash='/lattice/${id}'`)
    await waitFor(`document.querySelector('#title-${id}')&&!document.querySelector('.loading-message')`)
    if (id === 'basis-delegation') {
      const data = await catalog()
      const node = data.nodes.find(node => node.kyberAvailable)
      assert(node, 'An initialized Kyber node is required')
      await evaluate(`(()=>{const select=document.querySelector('#node-id');select.value=${JSON.stringify(node.id)};select.dispatchEvent(new Event('change',{bubbles:true}))})()`)
    }
    await waitFor(`document.querySelector('.execute-button')&&!document.querySelector('.execute-button').disabled`)
    await evaluate(`document.querySelector('.execute-button').click()`)
    await waitFor(`document.querySelector('.results-section .status.passed')&&!document.querySelector('.execute-button').disabled`)
    assert.equal(await evaluate(`document.querySelectorAll('.error-message').length`), 0)
    const data = await catalog()
    const result = data.records.find(row => row.caseId === id)
    assert(result?.passed && result.checks.every(row => row.passed))
    if (id === 'offline-trapdoor') generatedRoot = result.preparation.id
    if (id === 'basis-delegation') {
      assert.equal(result.preparation.parentId, generatedRoot, 'Delegation must use the just-generated root')
      delegated = result.preparation.id
    }
    if (id === 'parallel-sampling') {
      assert.equal(result.preparation.id, delegated, 'Sampling must use the just-delegated basis')
      assert.equal(result.valid, 32); assert(result.cleanupComplete && result.isolated)
      assert.equal(result.samples.length, 32)
      assert(result.samples.every(row => row.verified && row.norm <= row.bound && row.residual.every(n => n === 0)))
      assert.equal(result.executionMode, 'process')
      assert(result.workerSpans.every(span => span.kind === 'process'))
      assert(result.computeMs > 0 && result.poolSetupMs >= 0)
      assert.equal(await evaluate(`document.querySelectorAll('.samples tbody tr').length`), 32)
    }
    writeFileSync(join(output, id + '.json'), JSON.stringify(result, null, 2))
    results.push({ id, runId: result.id, passed: result.passed, checks: result.checks.length })
    await shot(id + '-desktop.png')
    for (const width of [768, 390]) {
      await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width === 390 })
      await delay(150)
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'Horizontal overflow: ' + id + ' ' + width)
      await shot(id + '-' + width + '.png')
    }
    await rpc('Emulation.clearDeviceMetricsOverride')
  }
  const sampling = []
  if (process.env.KMS_SAMPLING_BENCHMARK === '1') {
    for (const workers of [1, 4, 4, 1, 1, 4]) {
      const previous = (await catalog()).records.find(row => row.caseId === 'parallel-sampling')?.id
      await evaluate(`(()=>{const select=document.querySelector('#worker-count');select.value='${workers}';select.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('.execute-button').click()})()`)
      await waitFor(`document.querySelector('.execute-button')&&!document.querySelector('.execute-button').disabled&&!document.querySelector('.error-message')`)
      const row = (await catalog()).records.find(row => row.caseId === 'parallel-sampling')
      assert(row?.id !== previous && row?.passed && row?.executionMode === 'process')
      assert.equal(row.workers, workers)
      assert.equal(row.valid, 32)
      assert(row.cleanupComplete && row.checks.every(check => check.passed))
      assert.equal(row.usedWorkers, workers)
      sampling.push({ workers, samplingMs: row.samplingMs, computeMs: row.computeMs, poolSetupMs: row.poolSetupMs,
        poolReused: row.poolReused, totalMs: row.durationMs, runId: row.id })
      writeFileSync(join(output, `sampling-${sampling.length}-${workers}.json`), JSON.stringify(row, null, 2))
    }
    await shot('sampling-accelerated-desktop.png')
  }
  assert.deepEqual(errors, [])
  const summary = { verified: true, origin, cases: results, sampling, responsiveWidths: [1440, 768, 390], consoleErrors: errors }
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
  for (const request of pending.values()) clearTimeout(request.timer)
}
