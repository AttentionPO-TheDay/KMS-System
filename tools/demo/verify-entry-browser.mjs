// Frontend-only smoke against the built app. API fixtures are explicitly mocked;
// this is not backend authorization or deployment evidence.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const origin = process.env.KMS_FRONT_SMOKE_ORIGIN || 'http://127.0.0.1:5189'
const chromePath = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chromePath, 'Chrome or Edge is required')
const port = 9367
const profile = mkdtempSync(join(tmpdir(), 'kms-demo-front-'))
const chrome = spawn(chromePath, [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--headless=new', '--no-first-run', '--window-size=1600,1000', 'about:blank'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let ws, seq = 0
const pending = new Map()
const errors = []
const calls = []
let role = null, nodeId = null, returnNodeId = null, revision = 1, enabled = true, active = false
const context = () => ({ entryMode: 'DEMO', principalType: role, nodeId,
  returnNodeId, revision, enabled, csrfToken: 'fixture-csrf',
  node: nodeId ? { nodeId, name: nodeId, status: active ? 'ACTIVE' : 'PENDING_INIT' } : null })
const rpc = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq
  pending.set(id, { resolve, reject })
  ws.send(JSON.stringify({ id, method, params }))
})
const evaluate = async expression => {
  const reply = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (reply.exceptionDetails) throw new Error(JSON.stringify(reply.exceptionDetails))
  return reply.result?.value
}
const navigate = path => rpc('Page.navigate', { url: `${origin}/updatedel${path}` })
async function waitFor(expression, label) {
  for (let i = 0; i < 100; i++) {
    if (await evaluate(expression)) return
    await delay(100)
  }
  throw new Error(`Timed out: ${label}; ${await evaluate('document.body.innerText.slice(0,800)')}`)
}
const bodyHas = text => `document.body.innerText.includes(${JSON.stringify(text)})`
const click = text => evaluate(`(() => { const el=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()===${JSON.stringify(text)}); if(!el || el.disabled) return false; el.click(); return true })()`)
const envelope = data => ({ code: 200, data })

async function mocked(request) {
  const path = new URL(request.url).pathname
  const headers = Object.fromEntries(Object.entries(request.headers).map(([k,v]) => [k.toLowerCase(), v]))
  const data = request.postData ? JSON.parse(request.postData) : {}
  calls.push({ path, method: request.method, headers, data })
  if (path.startsWith('/demo-api/')) {
    assert.equal(headers.authorization, undefined, 'Demo must not inherit Admin-Token')
    if (!path.endsWith('/context') && !path.endsWith('/entry') && !path.endsWith('/admin') ||
        (request.method === 'POST' && role)) {
      assert.equal(headers['x-kms-demo-csrf'], 'fixture-csrf')
      assert.equal(headers['x-kms-demo-revision'], String(revision))
    }
  }
  if (path === '/demo-api/lifecycle/demo/context') return enabled ? envelope(context()) : { code: 403, msg: '受控演示未启用' }
  if (path === '/demo-api/lifecycle/demo/context/entry') {
    if (!['Node-A','Node-B'].includes(data.nodeId)) {
      role = null; nodeId = null; returnNodeId = null; revision++
      return { code: 403, msg: '节点不存在，不会自动创建', data: context() }
    }
    role = 'NODE'; nodeId = data.nodeId; returnNodeId = null; revision++
    return envelope(context())
  }
  if (path === '/demo-api/lifecycle/demo/context/admin') {
    if (role === 'NODE') returnNodeId = nodeId
    role = 'ADMIN'; nodeId = null; revision++
    return envelope(context())
  }
  if (path === '/demo-api/lifecycle/demo/context/node') {
    role = 'NODE'; nodeId = returnNodeId; revision++
    return envelope(context())
  }
  if (path === '/demo-api/lifecycle/demo/context/logout') { role = null; nodeId = null; returnNodeId = null; revision++; return envelope(context()) }
  if (path.endsWith('/getInfo')) {
    const principal = path.startsWith('/demo-api/') ? role : 'ADMIN'
    return { code: 200, user: { userId: principal === 'ADMIN' ? -1 : 20,
      userName: principal === 'ADMIN' ? 'ADMIN_FIXTURE' : nodeId, roleLevel: principal === 'ADMIN' ? 0 : 2,
      principalType: principal, avatar: '' }, roles: [principal === 'ADMIN' ? 'admin' : 'node'], permissions: ['*:*:*'] }
  }
  if (path.endsWith('/getRouters')) return envelope(role === 'ADMIN' ? [{ path: '/nodes', name: 'Nodes',
    component: 'Layout', meta: { title: '节点管理' }, children: [{ path: 'index', name: 'NodesIndex', component: 'nodes/index', meta: { title: '节点管理' } }] }] : [])
  if (path === '/demo-api/pqkds/node-self/') return envelope({ mapped: true,
    node: { nodeId, name: nodeId, status: active ? 'ACTIVE' : 'PENDING_INIT', keys: { kyber: active, falcon: active, sm2: active, sscl: active } } })
  if (path === '/demo-api/pqkds/node-self/keys/') return envelope({ nodeId, keys: active ? ['KYBER','SSCL','SM2','FALCON'].map(algorithm => ({
    algorithm, keyId: `${nodeId}-${algorithm}`, keyVersion: 1, publicKey: 'aabb', allowsNewWork: true })) : [] })
  if (path === '/demo-api/pqkds/nodes/') return envelope([{ id: 1, node_id: 'Node-A', name: 'Node A', status: 'active' }])
  if (path.endsWith('/captchaImage')) return { code: 200, captchaEnabled: false }
  // Dashboard reads are irrelevant to entry behavior; preserve the expected envelopes.
  return { code: 200, data: [], rows: [], total: 0 }
}

try {
  let target
  for (let i=0; i<60 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page') }
    catch { /* process startup */ }
    if (!target) await delay(100)
  }
  assert(target, 'browser started')
  ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }))
  ws.addEventListener('message', event => {
    const msg = JSON.parse(event.data)
    if (msg.id) {
      const request = pending.get(msg.id)
      if (!request) return
      pending.delete(msg.id)
      msg.error ? request.reject(new Error(JSON.stringify(msg.error))) : request.resolve(msg.result)
    } else if (msg.method === 'Fetch.requestPaused') {
      mocked(msg.params.request).then(body => rpc('Fetch.fulfillRequest', {
        requestId: msg.params.requestId, responseCode: 200,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        body: Buffer.from(JSON.stringify(body)).toString('base64')
      })).catch(error => { errors.push(error.message); rpc('Fetch.failRequest', { requestId: msg.params.requestId, errorReason: 'Failed' }).catch(()=>{}) })
    } else if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.text)
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Fetch.enable', { patterns: [{ urlPattern: '*api/*' }] })

  await navigate('/standalone/node/login')
  await waitFor(bodyHas('激活并登录'), 'node login alias')
  assert(await evaluate(`document.querySelector('input[placeholder="节点名称（如 Node-001）"]') !== null`))
  await navigate('/standalone/admin/login')
  await waitFor(`document.querySelector('input[placeholder="账号"]') !== null`, 'admin login alias')
  console.log('[PASS] standalone aliases preselect the original credential forms')
  await evaluate(`(async()=>{document.cookie='Admin-Token=standalone-fixture;path=/'; await new Promise((resolve,reject)=>{const r=indexedDB.open('kms-node-keystore',4); r.onupgradeneeded=()=>r.result.createObjectStore('meta',{keyPath:'k'}); r.onsuccess=()=>{const d=r.result; const tx=d.transaction('meta','readwrite'); tx.objectStore('meta').put({k:'smoke-sentinel',value:'standalone'}); tx.oncomplete=()=>{d.close();resolve()}};r.onerror=()=>reject(r.error)});})()`)

  await navigate('/standalone/node/login')
  await waitFor(`location.pathname.endsWith('/index') && !document.querySelector('.login-form')`, 'authenticated alias keeps server principal')
  await evaluate(`(()=>{const root=document.querySelector('#app').__vue_app__.config.globalProperties.$router;root.push('/standalone/node/login')})()`)
  await waitFor(`location.pathname.endsWith('/index') && !document.querySelector('.login-form')`, 'SPA alias cannot reuse old roles in a new credential form')
  console.log('[PASS] authenticated aliases do not expose a stale-role principal-switch form')

  await navigate('/demo')
  await waitFor(bodyHas('缺少节点 ID'), 'explicit missing node')
  assert(await evaluate(`document.querySelector('input[type=password]') === null`))
  await navigate('/demo?nodeId=Unknown')
  await waitFor(bodyHas('节点不存在'), 'nonexistent node refuses autocreation')
  assert(await click('管理控制台'))
  await waitFor(`location.pathname.endsWith('/demo/admin/index')`, 'failed-entry anonymous cookie can still explicitly enter admin')
  console.log('[PASS] nonexistent entry refreshes anonymous authority and keeps the admin exit usable')
  await navigate('/demo?nodeId=A%2FB')
  await waitFor(bodyHas('ASCII'), 'invalid node id')
  console.log('[PASS] Demo has no credential form and explicit missing/invalid/nonexistent node handling')

  await navigate('/demo?nodeId=Node-A')
  await waitFor(`location.pathname.endsWith('/demo/node/initialize') && ${bodyHas('Node-A')}`, 'pending init gate')
  assert(await evaluate(`document.cookie.includes('Admin-Token=standalone-fixture')`))
  assert(await evaluate(`(async()=>{const names=(await indexedDB.databases()).map(d=>d.name);return names.includes('kms-node-keystore')&&names.includes('kms-demo-node-keystore')})()`))
  console.log('[PASS] pending Demo uses isolated keystore without touching standalone token')

  assert(await click('管理控制台'))
  await waitFor(`location.pathname.endsWith('/demo/admin/index') && ${bodyHas('返回节点工作台')}`, 'admin full document boundary')
  assert.equal(role, 'ADMIN')
  assert(await evaluate(`!!document.querySelector('a[href="/updatedel/demo/admin/nodes/index"]')`), 'sys_menu paths are namespaced')
  await evaluate(`document.querySelector('a[href="/updatedel/demo/admin/nodes/index"]').click()`)
  await waitFor(bodyHas('Node A'), 'shared node management page')
  assert(!await evaluate(bodyHas('重签凭证')))
  assert(!await evaluate(bodyHas('批量生成 Falcon')))
  assert(await click('返回节点工作台'))
  await waitFor(`location.pathname.endsWith('/demo/node/initialize') && ${bodyHas('Node-A')}`, 'saved node restore')
  assert.equal(nodeId, 'Node-A')
  console.log('[PASS] role switches reset the document and shared menus; saved node is restored')

  const switches = calls.filter(c=>c.path.endsWith('/demo/context/admin')).length
  await navigate('/demo/admin/nodes/index')
  await waitFor(`location.pathname.endsWith('/demo/node/initialize')`, 'URL role is not authority')
  assert.equal(role, 'NODE')
  assert.equal(calls.filter(c=>c.path.endsWith('/demo/context/admin')).length, switches)
  console.log('[PASS] admin-looking URL cannot switch a NODE role')

  active = true
  await navigate('/demo?nodeId=Node-A')
  await waitFor(bodyHas('密钥材料需恢复，已禁止自动初始化或覆盖'), 'active missing keys block autogeneration')
  assert(!await evaluate(`!![...document.querySelectorAll('button')].find(b=>b.innerText.includes('开始初始化'))`))
  assert(!calls.some(c=>c.method==='POST' && c.path==='/demo-api/pqkds/node-self/keys/'))
  console.log('[PASS] ACTIVE without matching readable Demo keys is a non-overwriting recovery gate')

  role = null; nodeId = null; enabled = false
  await navigate('/demo')
  await waitFor(bodyHas('受控演示未启用'), 'disabled Demo')
  assert.equal(await evaluate(`!![...document.querySelectorAll('button')].find(b=>b.innerText==='管理控制台'&&b.disabled)`), true)
  assert(!calls.some(c=>c.path.startsWith('/lifecycle-api/')&&c.path.endsWith('/logout')))
  assert.deepEqual(errors, [])
  console.log('[PASS] disabled authority fails closed; no standalone logout or authorization fallback')
  console.log(`Frontend mocked browser smoke passed (${calls.length} API dispatches). Temporary profile: ${profile}`)
} finally {
  if (ws) ws.close()
  chrome.kill()
}
