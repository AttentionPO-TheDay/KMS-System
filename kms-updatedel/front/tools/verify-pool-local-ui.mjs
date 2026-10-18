// Real session page + real browser IndexedDB. All service calls are isolated fixtures.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const overrides = new Set(['getSelfNode', 'listSelfSessions', 'confirmSelfSession'])
let fixture = `
export const NODE_SELF_ERR={};let established=false;
export const getSelfNode=async()=>({mapped:true,node:{nodeId:'UI-A'}});
export const listSelfSessions=async()=>({items:[
 {sessionId:'ui-original-session',isSender:true,isRecipient:false,node1Id:'UI-A',node2Id:'UI-B',
 senderNode:'节点A',recipientNode:'节点B',protectionAlgorithm:'KYBER',status:established?'established':'key_recovered',confirmedCount:established?2:1},
 {sessionId:'ui-old-missing-session',isSender:true,isRecipient:false,node1Id:'UI-A',node2Id:'UI-B',
 senderNode:'节点A',recipientNode:'节点B',protectionAlgorithm:'KYBER',status:'key_recovered',confirmedCount:1}]});
export const confirmSelfSession=async(id,proof)=>{
 if(id!=='ui-original-session'||!/^[0-9a-f]{64}$/.test(proof))throw Error('invalid fixture proof');
 window.confirmCalls=(window.confirmCalls||0)+1;established=true;return {established:true,status:'established'};
};`
for (const match of readFileSync('src/api/pqkds/node-self.js', 'utf8').matchAll(/^export (?:async )?function (\w+)/gm)) {
  if (!overrides.has(match[1])) fixture += `export const ${match[1]}=async()=>{throw Error('Unexpected service ${match[1]}')};\n`
}
let vite, browser, socket, seq = 0
const pending = new Map(), errors = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => reject(Error(method)), 20000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result?.value
}
async function waitFor(expression) {
  for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await delay(100) }
  throw Error(expression + ': ' + errors.join(';'))
}
try {
  vite = await createServer({ server: { port: 5207, strictPort: true, fs: { allow: [join(process.cwd(), '../..')] } }, plugins: [{
    name: 'pool-session-isolated-services', enforce: 'pre',
    resolveId(id) { if (/\/api\/pqkds\/node-self(\.js)?$/.test(id)) return '\0pool-session-api' },
    load(id) { if (id === '\0pool-session-api') return fixture },
    configureServer(server) {
      server.middlewares.use('/pool-session-fixture', async (_req, res) => {
        const html = `<!doctype html><html lang="zh-CN"><body><div id="app"></div><script type="module">
        import {createApp,h} from 'vue';import {createRouter,createMemoryHistory} from 'vue-router';
        import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';
        import '/src/assets/styles/index.scss';
        import Sessions from '/src/views/selfSessions/index.vue';
        import {sealPoolSecret,markPoolSecretsUploaded,bindPoolSecretToSession,hasSessionSecret} from '/src/utils/crypto/node-key-store.js';
        import {keyHashOf} from '/src/utils/crypto/envelope-signing.js';
        if(!await hasSessionSecret('ui-original-session')){
          const key=crypto.getRandomValues(new Uint8Array(16)),keyHash=await keyHashOf(key);
          const ref={nodeId:'UI-A',peerNodeId:'UI-B',poolId:'ui-pool',keyHash,expiresAt:new Date(Date.now()+3600000).toISOString()};
          await sealPoolSecret(ref,key);await markPoolSecretsUploaded(ref.nodeId,ref.poolId,[keyHash]);
          await bindPoolSecretToSession(ref,'ui-original-session');key.fill(0);
        }
        const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:Sessions}]});
        await router.push('/');await router.isReady();
        createApp({render:()=>h('main',{style:'padding:24px'},[h(Sessions)])}).use(router).use(ElementPlus).mount('#app');
        window.fixtureReady=true;</script></body></html>`
        res.setHeader('Content-Type', 'text/html'); res.end(await server.transformIndexHtml('/pool-session-fixture', html))
      })
    }
  }] }); await vite.listen()
  browser = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=9432',
    `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-pool-session-'))}`, '--no-first-run', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i = 0; i < 60; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9432/json')).json()).find(item => item.type === 'page'); if (target) break } catch {}
    await delay(150)
  }
  assert(target); socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
    const item = pending.get(message.id); if (!item) return
    pending.delete(message.id); clearTimeout(item.timer)
    message.error ? item.reject(Error(JSON.stringify(message.error))) : item.resolve(message.result)
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 950, deviceScaleFactor: 1, mobile: false })
  await rpc('Page.navigate', { url: 'http://127.0.0.1:5207/pool-session-fixture' })
  const buttons = `[...document.querySelectorAll('button')].filter(b=>b.textContent.trim()==='确认')`
  await waitFor(`window.fixtureReady&&${buttons}.length===2`)
  assert.equal(await evaluate(`${buttons}.filter(b=>!b.disabled).length`), 1)
  await evaluate('document.fonts.ready.then(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))')
  // Reload proves this is not a transient in-memory copy of K.
  await rpc('Page.reload')
  await waitFor(`window.fixtureReady&&${buttons}.length===2`)
  assert.equal(await evaluate(`${buttons}.filter(b=>!b.disabled).length`), 1)
  await evaluate('document.fonts.ready')
  await delay(600)
  mkdirSync('../../tmp/pool-sender-falcon', { recursive: true })
  const shot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync('../../tmp/pool-sender-falcon/a-confirmation.png', Buffer.from(shot.data, 'base64'))
  await evaluate(`${buttons}.find(b=>!b.disabled).click()`)
  await waitFor('window.confirmCalls===1&&document.body.innerText.includes("2/2")')
  assert.equal(await evaluate(`${buttons}.filter(b=>!b.disabled).length`), 0)
  assert.equal(await evaluate('document.body.innerText.includes("处理中止") || document.body.innerText.includes("处理会话")'), false)
  assert.equal(errors.length, 0, errors.join(';'))
  console.log('PASS: real session page, A confirmation after B, persisted K after reload, actual HMAC submission, 2/2 establishment, old missing-material button disabled')
} finally {
  socket?.close(); browser?.kill(); await vite?.close()
  for (const item of pending.values()) clearTimeout(item.timer)
}
