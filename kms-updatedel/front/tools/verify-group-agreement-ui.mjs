// Three separate browser contexts + real Django service/SQLite via STDIN-only Docker.
// Fixture identities and channels only; never contacts the running business services.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createServer } from 'vite'
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const pending = new Map(), sockets = [], contexts = [], errors = []
let sequence = 0, backend, backendLines, browser, vite, browserSocket
let stderr = ''
function backendRpc(command) {
  return new Promise((resolve, reject) => {
    const id = ++sequence
    const timer = setTimeout(() => { pending.delete(id); reject(Error('Offline backend timed out: ' + stderr.slice(-1000))) }, 30000)
    pending.set(id, { resolve, reject, timer })
    backend.stdin.write(JSON.stringify({ id, ...command }) + '\n')
  })
}
async function connect(url, isPage = true) {
  const socket = new WebSocket(url)
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }) })
  sockets.push(socket)
  let seq = 0
  const requests = new Map()
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
    if (message.method === 'Network.requestWillBeSent') {
      const url = message.params.request.url
      if (/^https?:/.test(url) && !url.startsWith('http://127.0.0.1:5201/')) errors.push('Unexpected network origin: ' + new URL(url).origin)
    }
    const request = requests.get(message.id)
    if (!request) return
    requests.delete(message.id); clearTimeout(request.timer)
    message.error ? request.reject(Error(JSON.stringify(message.error))) : request.resolve(message.result)
  })
  const rpc = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => { requests.delete(id); reject(Error(method)) }, 15000)
    requests.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async expression => {
    const response = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    assert(!response.exceptionDetails, JSON.stringify(response.exceptionDetails))
    return response.result?.value
  }
  const waitFor = async expression => {
    for (let attempt = 0; attempt < 120; attempt++) { if (await evaluate(expression)) return; await delay(100) }
    throw Error('UI condition failed: ' + expression + ' ' + await evaluate('document.body.innerText.slice(-1200)'))
  }
  const clickText = async text => {
    // A completed backend round may precede the UI's finally/refresh by a tick.
    for (let attempt = 0; attempt < 120; attempt++) {
      if (await evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(button=>button.innerText.trim()===${JSON.stringify(text)}&&!button.disabled);if(!button)return false;button.click();return true})()`)) return
      await delay(100)
    }
    throw Error('Missing enabled button: ' + text)
  }
  if (isPage) { await rpc('Runtime.enable'); await rpc('Page.enable'); await rpc('Network.enable') }
  return { rpc, evaluate, waitFor, clickText }
}

try {
  const backendPath = resolve('../../kms-distribute/dvadmin/backend')
  backend = spawn('docker', ['run', '--rm', '--pull', 'never', '-i', '--network', 'none', '--entrypoint', 'python',
    '--mount', `type=bind,source=${backendPath},target=/backend,readonly`, '-w', '/backend',
    '-e', 'PYTHONDONTWRITEBYTECODE=1', 'kms-dvadmin3-django:local', '-u', 'tests/group_agreement_rpc_fixture.py'],
    { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
  backend.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-3000) })
  backendLines = createInterface({ input: backend.stdout })
  backendLines.on('line', line => {
    let message
    try { message = JSON.parse(line) } catch { stderr = (stderr + line).slice(-3000); return }
    const request = pending.get(message.id)
    if (!request) return
    pending.delete(message.id); clearTimeout(request.timer)
    message.error ? request.reject(Error(message.error)) : request.resolve(message.result)
  })
  const fixture = await backendRpc({ op: 'init' })
  const api = `
    async function call(op,agreementId,payload){const r=await fetch('/isolated-group-api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op,agreementId,payload,nodeId:new URLSearchParams(location.search).get('node')})});const data=await r.json();if(data.error)throw Error(data.error);return data.result}
    export const listGroupAgreements=()=>call('list');export const createGroupAgreement=participantNodeIds=>call('create',undefined,{participantNodeIds});
    export const getGroupAgreement=id=>call('detail',id);export const actOnGroupAgreement=(id,action,payload={})=>call('act',id,{action,...payload});`
  vite = await createServer({ cacheDir: mkdtempSync(join(tmpdir(), 'kms-group-vite-cache-')), server: { port: 5201, strictPort: true, fs: { allow: [resolve('../..')] } }, plugins: [{
    name: 'isolated-group-qa', enforce: 'pre',
    resolveId(id) { if (/\/api\/pqkds\/group-agreement(\.js)?$/.test(id)) return '\0group-api-fixture' },
    load(id) { if (id === '\0group-api-fixture') return api },
    configureServer(server) {
      server.middlewares.use('/isolated-group-api', async (request, response) => {
        try {
          let body = ''; for await (const chunk of request) body += chunk
          response.setHeader('Content-Type', 'application/json')
          response.end(JSON.stringify({ result: await backendRpc(JSON.parse(body)) }))
        } catch (error) { response.end(JSON.stringify({ error: error.message })) }
      })
      server.middlewares.use('/isolated-group', async (_request, response) => {
        const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="app" class="app-container"></div><script type="module">
          import {createApp,h} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';import '/src/assets/styles/index.scss';
          import {KEYSTORE_DB_NAME} from '/src/utils/entry-mode.js';
          const fixture=${JSON.stringify(fixture)};const node=new URLSearchParams(location.search).get('node');
          const channels=fixture.channels.filter(channel=>channel.left===node||channel.right===node);
          // Seed an actual v4 encrypted store, then let production code upgrade it to v5.
          const protector=await crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);
          const rows=await Promise.all(channels.map(async channel=>{const bytes=Uint8Array.from(channel.secret.match(/../g),x=>parseInt(x,16)),iv=crypto.getRandomValues(new Uint8Array(12));const sealed=await crypto.subtle.encrypt({name:'AES-GCM',iv},protector,bytes);bytes.fill(0);return {sessionId:channel.sessionId,iv,sealed,createdAt:new Date().toISOString()}}));
          await new Promise((resolve,reject)=>{const req=indexedDB.open(KEYSTORE_DB_NAME,4);req.onupgradeneeded=()=>{for(const [name,keyPath]of [['meta','k'],['keys','keyRef'],['deviceKeys','keyRef'],['sessionKeys','sessionId']])req.result.createObjectStore(name,{keyPath})};req.onerror=()=>reject(req.error);req.onsuccess=()=>{const db=req.result,tx=db.transaction(['meta','sessionKeys'],'readwrite');tx.objectStore('meta').put({k:'protector',key:protector});for(const row of rows)tx.objectStore('sessionKeys').put(row);tx.oncomplete=()=>{db.close();resolve()};tx.onerror=()=>reject(tx.error)}});
          window.__store=await import('/src/utils/crypto/node-key-store.js');window.__dbName=KEYSTORE_DB_NAME;
          const {default:Group}=await import('/src/views/selfSessions/GroupAgreement.vue');createApp({render:()=>h(Group)}).use(ElementPlus).mount('#app');window.__ready=true;
        </script></body></html>`
        response.setHeader('Content-Type', 'text/html')
        response.end(await server.transformIndexHtml('/isolated-group', html))
      })
    }
  }] })
  await vite.listen()
  browser = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=9422',
    `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-group-qa-'))}`, '--no-first-run', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let version
  for (let attempt = 0; attempt < 80; attempt++) {
    try { version = await (await fetch('http://127.0.0.1:9422/json/version')).json(); break } catch { await delay(150) }
  }
  assert(version)
  browserSocket = await connect(version.webSocketDebuggerUrl, false)
  const pages = []
  for (const node of fixture.nodes) {
    const { browserContextId } = await browserSocket.rpc('Target.createBrowserContext'); contexts.push(browserContextId)
    const { targetId } = await browserSocket.rpc('Target.createTarget', { url: 'about:blank', browserContextId })
    const targets = await (await fetch('http://127.0.0.1:9422/json')).json()
    const target = targets.find(item => item.id === targetId); assert(target)
    const page = await connect(target.webSocketDebuggerUrl)
    await page.rpc('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1000, deviceScaleFactor: 1, mobile: false })
    await page.rpc('Page.navigate', { url: `http://127.0.0.1:5201/isolated-group?node=${encodeURIComponent(node.nodeId)}` })
    await page.waitFor('window.__ready===true&&document.querySelectorAll(".agreement-toolbar .el-select").length===1')
    pages.push({ ...page, nodeId: node.nodeId })
  }
  const [a, b, c] = pages
  async function createThroughUI() {
    await a.evaluate(`document.querySelector('.agreement-toolbar .el-select__wrapper').click()`)
    await a.waitFor(`document.querySelectorAll('.el-select-dropdown__item').length===2`)
    for (const node of fixture.nodes.slice(1)) {
      await a.evaluate(`[...document.querySelectorAll('.el-select-dropdown__item')].find(e=>e.innerText.includes(${JSON.stringify(node.nodeId)})).click()`)
    }
    await a.evaluate(`document.body.click()`)
    await a.clickText('发起多方协商')
    await a.waitFor(`document.querySelector('.agreement-detail')&&document.querySelector('.agreement-detail').innerText.includes('生成随机贡献并提交承诺')`)
    return (await backendRpc({ op: 'list', nodeId: a.nodeId })).items[0].agreementId
  }
  const gid = await createThroughUI()
  async function selectGroup(page, id) {
    await page.clickText('刷新')
    await page.waitFor(`[...document.querySelectorAll('.el-table__row')].some(row=>row.innerText.includes(${JSON.stringify(id)})&&row.querySelector('button')&&!row.querySelector('button').disabled)`)
    await page.evaluate(`[...document.querySelectorAll('.el-table__row')].find(row=>row.innerText.includes(${JSON.stringify(id)})).querySelector('button').click()`)
    await page.waitFor(`document.querySelector('.agreement-detail')?.innerText.includes(${JSON.stringify(id)})`)
  }
  await selectGroup(b, gid); await selectGroup(c, gid)
  async function round(text, stage, agreementId = gid) {
    for (const page of pages) {
      await page.clickText('刷新')
      await page.waitFor(`[...document.querySelectorAll('.agreement-detail button')].some(e=>e.innerText.trim()===${JSON.stringify(text)}&&!e.disabled)`)
      await page.clickText(text)
      await page.waitFor(`document.querySelector('.agreement-detail')&&!document.querySelector('.agreement-detail .el-button.is-loading')&&document.querySelector('.agreement-detail').innerText.includes('本节点')`)
      // Backend is the round oracle, not a successful toast or animated progress.
      for (let attempt = 0; attempt < 80; attempt++) {
        const data = await backendRpc({ op: 'detail', nodeId: page.nodeId, agreementId })
        if (data.members.find(member => member.nodeId === page.nodeId)[stage]) break
        if (attempt === 79) throw Error('Member round did not reach backend')
        await delay(100)
      }
    }
  }
  await round('生成随机贡献并提交承诺', 'committedAt')
  for (const page of pages) {
    const state = await page.evaluate(`window.__store.readAgreementState(${JSON.stringify(gid)},${JSON.stringify(page.nodeId)}).then(s=>Boolean(s?.contribution?.length===64))`)
    assert(state)
  }
  await round('加密发送本节点贡献', 'exchangedAt')
  await round('校验贡献、派生密钥并确认', 'confirmedAt')
  const final = await backendRpc({ op: 'detail', nodeId: a.nodeId, agreementId: gid })
  assert.equal(final.status, 'established'); assert.equal(final.confirmedCount, 3)
  const keys = []
  for (const page of pages) {
    await page.clickText('刷新')
    await page.waitFor(`document.querySelector('.agreement-detail')?.innerText.includes('全员确认一致，协商已建立')`)
    keys.push(await page.evaluate(`window.__store.unsealSessionSecret(${JSON.stringify(gid)}).then(bytes=>Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join(''))`))
    assert(await page.evaluate(`window.__store.unsealSessionSecret(${JSON.stringify(fixture.channels.find(channel=>channel.left===page.nodeId||channel.right===page.nodeId).sessionId)}).then(bytes=>bytes.length===16)`))
    assert.equal(await page.evaluate(`window.__store.readAgreementState(${JSON.stringify(gid)},${JSON.stringify(page.nodeId)})`), null)
  }
  assert.equal(new Set(keys).size, 1)
  assert.equal(keys[0].length, 32)
  const out = resolve('../../tmp/group-agreement'); mkdirSync(out, { recursive: true })
  for (const width of [1500, 390]) {
    await a.rpc('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: false }); await delay(300)
    assert(await a.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
    const shot = await a.rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    writeFileSync(join(out, `group-${width}.png`), Buffer.from(shot.data, 'base64'))
  }
  // A real close is terminal; the local contribution and derived-key copies are removed.
  await a.clickText('关闭协商')
  await a.waitFor(`document.querySelector('.el-message-box__btns .el-button--primary')`)
  await a.evaluate(`document.querySelector('.el-message-box__btns .el-button--primary').click()`)
  await a.waitFor(`document.querySelector('.agreement-detail')?.innerText.includes('已关闭')`)
  assert.equal((await backendRpc({ op: 'detail', nodeId: b.nodeId, agreementId: gid })).status, 'closed')
  await b.clickText('刷新'); await c.clickText('刷新')
  for (const page of pages) await page.waitFor(`window.__store.hasSessionSecret(${JSON.stringify(gid)}).then(found=>!found)`)
  // Corrupt an actual encrypted packet in the isolated database. No fake success UI.
  const failing = await backendRpc({ op: 'create', nodeId: a.nodeId,
    payload: { participantNodeIds: [b.nodeId, c.nodeId] } })
  for (const page of pages) await selectGroup(page, failing.agreementId)
  await round('生成随机贡献并提交承诺', 'committedAt', failing.agreementId)
  await round('加密发送本节点贡献', 'exchangedAt', failing.agreementId)
  await backendRpc({ op: 'tamper', nodeId: c.nodeId, agreementId: failing.agreementId })
  await c.clickText('刷新')
  await c.waitFor(`[...document.querySelectorAll('.agreement-detail button')].some(e=>e.innerText.trim()==='校验贡献、派生密钥并确认'&&!e.disabled)`)
  await c.clickText('校验贡献、派生密钥并确认')
  await c.waitFor(`document.querySelector('.agreement-error')?.innerText.includes('贡献密文认证失败')`)
  const rejected = await backendRpc({ op: 'detail', nodeId: c.nodeId, agreementId: failing.agreementId })
  assert.equal(rejected.status, 'confirming'); assert.equal(rejected.confirmedCount, 0)
  assert(!await c.evaluate(`document.querySelector('.agreement-detail').innerText.includes('全员确认一致，协商已建立')`))
  assert(!await c.evaluate(`window.__store.hasSessionSecret(${JSON.stringify(failing.agreementId)})`))
  await c.clickText('关闭协商')
  await c.waitFor(`document.querySelector('.el-message-box__btns .el-button--primary')`)
  await c.evaluate(`document.querySelector('.el-message-box__btns .el-button--primary').click()`)
  await c.waitFor(`document.querySelector('.agreement-detail')?.innerText.includes('已关闭')`)
  assert.equal(errors.length, 0, errors.join(';'))
  console.log('PASS: 三个隔离浏览器节点 + 真实Django状态机；本机随机贡献、加密交换、全员派生相同密钥、3/3确认、v4→v5加密库升级保留旧密钥、终态清理、桌面/手机布局、真实密文篡改拒绝且无假成功；无真实业务写入')
} finally {
  for (const socket of sockets) socket.close()
  browser?.kill(); await vite?.close()
  backend?.stdin.end(); backendLines?.close()
  for (const request of pending.values()) { clearTimeout(request.timer); request.reject(Error('Fixture stopped')) }
  pending.clear()
}
