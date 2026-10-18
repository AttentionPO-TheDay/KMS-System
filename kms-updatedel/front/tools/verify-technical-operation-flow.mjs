// Isolated desktop UI checks; no production API or cryptographic material.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createTechnicalTrace, startTechnicalTrace, recordTechnicalTrace, finishTechnicalTrace } from '../src/utils/technical-operation-trace.js'
await import('./verify-technical-operation-linkage.mjs')

const trace = createTechnicalTrace()
startTechnicalTrace(trace, { poolId: 'pool_fixture', requested: 100, secretKey: 'NEVER_DISPLAY', keyHex: 'NEVER_DISPLAY' })
assert.equal(trace.facts.secretKey, undefined)
recordTechnicalTrace(trace, '响应', { accepted: 90, rejected: 10 })
finishTechnicalTrace(trace, 'partial', '部分完成')
recordTechnicalTrace(trace, '晚到记录', { accepted: 100 })
assert.equal(trace.facts.accepted, 90)
assert.equal(trace.events.length, 3)
startTechnicalTrace(trace, { keyId: 'second' })
assert.equal(trace.facts.poolId, undefined)
assert.equal(trace.events.length, 1)
for (let i = 0; i < 100; i++) recordTechnicalTrace(trace, '记录')
assert.equal(trace.events.length, 40)
for (const [page, kind] of [['preallocate', 'preallocation'], ['distribute', 'distribution'], ['keyupdate', 'update']]) {
  const source = readFileSync(`src/views/${page}/index.vue`, 'utf8')
  assert(source.includes(`ref="technicalFlow" kind="${kind}"`))
  assert(source.includes('technicalFlow.value?.start('))
  assert(source.includes('technicalFlow.value?.stage('))
  assert(source.includes("technicalFlow.value?.finish('failed'"))
}

let server, browser, socket, seq = 0
const pending = new Map(), errors = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => reject(Error(method)), 15000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails))
  return result.result?.value
}
try {
  server = await createServer({ server: { port: 5203, strictPort: true, fs: { allow: [join(process.cwd(), '../..')] } }, plugins: [{
    name: 'operation-flow-fixture',
    configureServer(instance) {
      instance.middlewares.use('/operation-fixture', async (_req, res) => {
        const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head><body><div id="app"></div><script type="module">
        import {createApp,h,ref} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';
        import Technical from '/src/components/TechnicalView/index.vue';
        window.flows={};createApp({setup(){const refs={preallocation:ref(null),distribution:ref(null),update:ref(null)};
        window.flows=refs;return()=>h('main',{style:'padding:24px;max-width:1200px;margin:auto'},Object.entries(refs).map(([kind,r])=>h(Technical,{kind,ref:r})))}}).use(ElementPlus).mount('#app');window.ready=true;
        </script></body></html>`
        res.setHeader('Content-Type', 'text/html'); res.end(await instance.transformIndexHtml('/operation-fixture', html))
      })
    }
  }] }); await server.listen()
  browser = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=9426', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-operation-'))}`, '--no-first-run', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i = 0; i < 60; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9426/json')).json()).find(r => r.type === 'page'); if (target) break } catch {}
    await delay(200)
  }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
    const item = pending.get(message.id); if (!item) return
    pending.delete(message.id); clearTimeout(item.timer)
    message.error ? item.reject(Error(JSON.stringify(message.error))) : item.resolve(message.result)
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1100, deviceScaleFactor: 1, mobile: false })
  await rpc('Page.navigate', { url: 'http://127.0.0.1:5203/operation-fixture' })
  for (let i = 0; i < 100; i++) { if (await evaluate('window.ready===true')) break; await delay(100) }
  assert(await evaluate('window.ready===true'))
  assert.equal(await evaluate('document.querySelectorAll(".operation-flow").length'), 0)
  await evaluate(`flows.preallocation.value.start({nodeId:'NODE-A',peerNodeId:'NODE-B',poolId:'pool_fixture_001',requested:100,secretKey:'NEVER_DISPLAY'});
    flows.preallocation.value.stage('peer','success','接收公钥及版本已取得',{keyId:'KYBER-fixture',version:2});
    flows.preallocation.value.stage('prepare','success','本机保护包全部准备完成',{generated:100,wrapped:100,signed:100});
    flows.preallocation.value.stage('submit','partial','服务端批次入池响应',{uploaded:100,accepted:90,rejected:10});
    flows.preallocation.value.finish('partial','本次预分配响应汇总');
    flows.distribution.value.start({batchId:'batch_fixture_002',peerNodeId:'NODE-B',keyId:'KYBER-fixture',version:2});
    for(const id of ['prepare','wrap','sign','submit']) flows.distribution.value.stage(id,'success','步骤完成',{sessionId:'session_fixture',sessionStatus:'initiated'});
    flows.distribution.value.stage('store','partial','本地保存失败，等待处理',{keyStored:false});
    flows.distribution.value.finish('partial','本地保存失败，等待处理',{keyStored:false});
    flows.update.value.start({keyId:'FALCON-fixture',version:2,nextVersion:3});
    flows.update.value.stage('identity','success','节点身份及版本校验完成');
    flows.update.value.stage('material','success','新版本已在本机封存');
    flows.update.value.stage('selftest','failed','本机材料自检未通过',{selfTestOk:false});
    flows.update.value.finish('failed','更新失败');`)
  await delay(200)
  assert.equal(await evaluate('document.querySelectorAll(".operation-flow").length'), 3)
  assert(!await evaluate('document.body.innerText.includes("NEVER_DISPLAY")'))
  for (const text of ['并行抽样短向量', '离线生成格陷门', '快速委派格基向量', '部分完成', '执行失败', 'session_fixture', '待双方确认', '本机材料自检未通过']) {
    assert(await evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`), text)
  }
  for (const text of ['技术流程映射', '不代表对应算法已执行', '开始演示', 'NEVER_DISPLAY']) {
    assert(!await evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`), text)
  }
  assert.equal(await evaluate('document.querySelectorAll("[data-stage=register][data-status=pending]").length'), 1)
  assert.equal(await evaluate('document.querySelectorAll("[data-stage=store][data-status=partial]").length'), 1)
  assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'))
  mkdirSync('../../tmp/technical-operation', { recursive: true })
  const shot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync('../../tmp/technical-operation/desktop.png', Buffer.from(shot.data, 'base64'))
  await evaluate(`flows.preallocation.value.start({poolId:'new_pool',requested:1});
    for(const id of ['peer','prepare','submit']) flows.preallocation.value.stage(id,'success','步骤完成');
    flows.preallocation.value.finish('success','入池完成',{accepted:1});`)
  await delay(100)
  assert(!await evaluate('document.querySelector(".operation-flow").innerText.includes("pool_fixture_001")'))
  assert(await evaluate('document.querySelector(".operation-flow").innerText.includes("已完成 3 / 3")'))
  await evaluate(`flows.distribution.value.start({peerNodeId:'NODE-B'},{mode:'pool'});flows.distribution.value.stage('consume','running','等待取用回执');`)
  await delay(100)
  assert.equal(await evaluate('document.querySelectorAll("[data-stage=consume][data-status=running]").length'), 1)
  assert.equal(await evaluate('document.querySelectorAll("[data-stage=wrap]").length'), 0)
  assert.equal(errors.length, 0, errors.join(';'))
  console.log('PASS: desktop stage layout, partial/failure/reset, pool mode, identifier whitelist and page hooks')
} finally {
  socket?.close(); browser?.kill(); await server?.close()
  for (const item of pending.values()) clearTimeout(item.timer)
}
