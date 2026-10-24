// Render actual recorded evaluator/gateway evidence in the current components.
// This is an isolated read-only result replay, not a claim of remote deployment.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('../', import.meta.url))
const evidenceDir = resolve(root, '../../output/quantum-attack-research')
const ids = ['quantum-lwe-usvp', 'quantum-lwe-bdd', 'quantum-lwe-dual']
const results = ids.map(id => JSON.parse(readFileSync(join(evidenceDir, `${id}-run.json`), 'utf8')))
assert(results.every(r => r.status === 'completed' && r.quantumEvidence?.evaluationComplete && !r.passed))
const source = `
import {createApp} from 'vue';
import Workbench from '/src/components/AcceptanceWorkbench.vue';
import {acceptanceCriteria,securityRuns,health} from '/src/store/index.js';
import '/src/style.scss';
acceptanceCriteria.value=[{id:'quantum-attacks',kind:'security-suite',title:'量子攻击仿真与参数评估',requirement:'系统能够抵御量子攻击种类不少于3种',target:3,operator:'>=',unit:'种',caseIds:${JSON.stringify(ids)},evidenceSource:'本地实际执行证据回放'}];
securityRuns.value=${JSON.stringify(results)};
health.value={securityExecutionAvailable:true};
createApp(Workbench).mount('#app');`
const server = await createServer({ root, server: { host: '127.0.0.1', port: 5187, strictPort: true, fs: { allow: [resolve(root, '../..')] } },
  plugins: [{ name: 'quantum-result-replay',
    resolveId(id) { if (id === 'virtual:quantum-review') return '\0quantum-review' },
    load(id) { if (id === '\0quantum-review') return source },
    configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        if (req.url !== '/quantum-review') return next()
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end(await vite.transformIndexHtml('/quantum-review', '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body class="dark-theme" style="padding:24px"><p style="margin-bottom:20px">本地实际执行结果回放</p><div id="app"></div><script type="module">import "virtual:quantum-review"</script></body></html>'))
      })
    }
  }] })
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const pending = new Map(), errors = []
let browser, socket, sequence = 0
function rpc(method, params = {}) {
  const id = ++sequence
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)) }, 20000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const r = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text)
  return r.result?.value
}
try {
  await server.listen()
  browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=9407', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-quantum-ui-'))}`, '--no-first-run', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i = 0; i < 60; i++) { try { target = (await (await fetch('http://127.0.0.1:9407/json')).json()).find(t => t.type === 'page'); if (target) break } catch {} await delay(200) }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const m = JSON.parse(event.data)
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
    const request = pending.get(m.id); if (!request) return
    pending.delete(m.id); clearTimeout(request.timer)
    m.error ? request.reject(new Error(m.error.message)) : request.resolve(m.result)
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1200, deviceScaleFactor: 1, mobile: false })
  await rpc('Page.navigate', { url: 'http://127.0.0.1:5187/quantum-review' })
  for (let i = 0; i < 100; i++) { if (await evaluate(`document.querySelectorAll('.quantum-evidence tbody tr').length===9`)) break; await delay(200) }
  assert.equal(await evaluate(`document.querySelectorAll('.quantum-evidence tbody tr').length`), 9)
  assert(await evaluate(`document.body.innerText.includes('评估完成，指标待核验')`))
  assert.equal(await evaluate(`document.querySelectorAll('.security-result.passed').length`), 0)
  await evaluate(`document.querySelectorAll('.quantum-evidence details').forEach(e=>e.open=true)`)
  await delay(300)
  mkdirSync(join(evidenceDir, 'ui'), { recursive: true })
  for (const [name, width, height] of [['desktop', 1680, 1200], ['mobile', 390, 844]]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 })
    await delay(200)
    assert(await evaluate(`document.documentElement.scrollWidth<=window.innerWidth+1`), `${name}: document overflow`)
    const shot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    writeFileSync(join(evidenceDir, 'ui', `${name}.png`), Buffer.from(shot.data, 'base64'))
  }
  assert.equal(errors.length, 0, errors.join('; '))
  console.log('PASS: 实际记录回放，9行参数成本、展开电路证据、无误判通过、桌面/390px布局、无浏览器异常')
} finally {
  socket?.close(); browser?.kill(); for (const r of pending.values()) clearTimeout(r.timer)
  await server.close()
}
