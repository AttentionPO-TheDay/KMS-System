// Isolated UI fixtures only: synthetic API data, no production server or key writes.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome, 'Chrome/Edge required')
const fixture = `
const node={nodeId:'TEST_ONLY_UI',status:'ACTIVE',falconClCapability:{enabled:true}};
export const NODE_SELF_ERR={};
export const getSelfNode=async()=>({mapped:true,node});
export const listSelfNodeKeys=async()=>({nodeId:node.nodeId,keys:[]});
export const listSelfSessions=async()=>({nodeId:node.nodeId,sessions:[]});
export const closeSelfSession=async()=>{throw Error('No mutation')};
export const confirmSelfSession=closeSelfSession;
export const getSessionVersions=closeSelfSession;
export const listSelfEnvelopes=closeSelfSession;
export const recoverEnvelope=closeSelfSession;
export const verifyEnvelope=closeSelfSession;
export const cryptoProvider={inspectNodeKeys:async()=>({keys:[]}),selfTest:async()=>({ok:true}),hasKey:async()=>false};
export const generateAndRegisterNodeKey=async request=>{window.__requests.push({algorithm:request.algorithm,nodeId:request.nodeId});return {material:{keyRef:'TEST_ONLY'},check:{ok:true}}};
`
let server, browser, socket, seq = 0
const pending = new Map(), errors = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
function rpc(method, params = {}) {
  const id = ++seq
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)) }, 15000)
    pending.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const response = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!response.exceptionDetails, response.exceptionDetails?.text)
  return response.result?.value
}
async function waitFor(expression) {
  for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await delay(100) }
  throw new Error(`UI timeout: ${expression}`)
}
try {
  server = await createServer({ server: { port: 5192, strictPort: true }, plugins: [{
    name: 'isolated-generation-purpose', enforce: 'pre',
    resolveId(id) {
      if (/\/api\/pqkds\/node-self(?:\.js)?$|\/utils\/crypto\/browser-provider(?:\.js)?$|\/utils\/node-initialization(?:\.js)?$/.test(id)) return '\0test-purpose'
    },
    load(id) { if (id === '\0test-purpose') return fixture },
    configureServer(instance) {
      instance.middlewares.use('/purpose-fixture', async (_req, res) => {
        const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head><body><div id="app"></div><script type="module">
        import {createApp,h} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';
        import {createRouter,createMemoryHistory,RouterView} from 'vue-router';
        import Generation from '/src/views/generate/create.vue';import Sessions from '/src/views/selfSessions/index.vue';
        import {setEntryPrincipal} from '/src/utils/entry-mode.js';setEntryPrincipal('NODE');window.__requests=[];
        const router=createRouter({history:createMemoryHistory(),routes:[{path:'/genzone/create',component:Generation},{path:'/demo/node/distzone/selfsess',component:Sessions}]});
        await router.push('/genzone/create');await router.isReady();window.__router=router;
        createApp({render:()=>h(RouterView)}).use(router).use(ElementPlus).mount('#app');
        </script></body></html>`
        res.setHeader('Content-Type', 'text/html');res.end(await instance.transformIndexHtml('/purpose-fixture', html))
      })
    }
  }] })
  await server.listen()
  browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=9402', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-purpose-ui-'))}`, '--no-first-run', '--window-size=1500,1100', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i = 0; i < 60; i++) { try { target = (await (await fetch('http://127.0.0.1:9402/json')).json()).find(row => row.type === 'page'); if (target) break } catch {} await delay(200) }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
    const request = pending.get(message.id)
    if (!request) return
    pending.delete(message.id);clearTimeout(request.timer)
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result)
  })
  await rpc('Runtime.enable');await rpc('Page.enable')
  await rpc('Page.navigate', { url: 'http://127.0.0.1:5192/purpose-fixture' })
  await waitFor(`document.querySelectorAll('.gen-create__algo').length===4`)
  assert(!await evaluate(`document.querySelector('.gen-create__grid').innerText.includes('标准 Falcon 会话签名密钥')`))
  assert(await evaluate(`document.querySelector('.gen-create__grid').innerText.includes('改进型无证书格加密')`))
  await evaluate(`[...document.querySelectorAll('.gen-create__algo')].find(el=>el.innerText.includes('改进型无证书格加密')).querySelector('button').click()`)
  await waitFor(`window.__requests.length===1`)
  assert.equal(await evaluate(`window.__requests[0].algorithm`), 'FALCON_CL_V1')
  const protectionScreenshot = await rpc('Page.captureScreenshot', { format: 'png' })
  writeFileSync('.generation-purpose-protection.png', Buffer.from(protectionScreenshot.data, 'base64'))
  await evaluate(`document.querySelector('.gen-create__lead a').click()`)
  await waitFor(`document.querySelectorAll('.gen-create__algo').length===1&&document.body.innerText.includes('标准 Falcon 会话签名密钥')`)
  assert.equal(await evaluate(`window.__router.currentRoute.value.query.keyPurpose`), 'signing')
  await evaluate(`document.querySelector('.gen-create__algo button').click()`)
  await waitFor(`window.__requests.length===2`)
  assert.equal(await evaluate(`window.__requests[1].algorithm`), 'FALCON')
  const signatureScreenshot = await rpc('Page.captureScreenshot', { format: 'png' })
  writeFileSync('.generation-purpose-signing.png', Buffer.from(signatureScreenshot.data, 'base64'))
  await evaluate(`[...document.querySelectorAll('.el-tabs__item')].find(el=>el.innerText==='会话列表').click()`)
  await waitFor(`!document.querySelector('.gen-create__algo')&&document.body.innerText.includes('没有符合条件的会话')`)
  assert.equal(errors.length, 0, errors.join('; '))
  console.log('PASS: real browser rendering, encryption/signature generation request isolation, purpose link, session tab return; synthetic data only')
} finally {
  socket?.close();browser?.kill();await server?.close()
}
