/** Real browser Demo entry/initialization smoke (no mocked successful business responses).
 * Requires the explicitly enabled loopback Demo gateway and deployed frontend.
 * Runs in a new temporary Chrome profile, creates uniquely named nodes and deletes only those nodes.
 * One SM2 registration is deliberately interrupted to prove resumability; no production data is reset.
 * Usage: node tools/verify-demo-entry-ui.mjs
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = process.env.KMS_DEMO_UI_ORIGIN || 'http://127.0.0.1:8088'
const STANDALONE = process.env.KMS_STANDALONE_UI_ORIGIN || 'http://127.0.0.1'
assert.equal(new URL(ORIGIN).hostname, '127.0.0.1', 'only an explicitly enabled loopback test gateway is supported')
const BASE = '/updatedel'
const CDP_PORT = Number(process.env.KMS_DEMO_UI_CDP_PORT || 9397)
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(CHROME, 'Chrome or Edge is required')
const seed = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`.toUpperCase()
const nodeIds = [`Demo-UI-A-${seed}`, `Demo-UI-B-${seed}`]
const owned = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex')
const requireOk = (response, label) => {
  if (![200,2000].includes(response?.body?.code)) throw new Error(`${label}: HTTP=${response?.status}, ${JSON.stringify(response?.body)}`)
  return response.body.data
}
const check = (label, actual, detail = '') => {
  console.log(`${actual ? '[PASS]' : '[FAIL]'} ${label}${detail ? ` — ${detail}` : ''}`)
  assert(actual, label)
}

function connect(url, onEvent = () => {}) {
  const ws = new WebSocket(url)
  let seq = 0
  const pending = new Map()
  const ready = new Promise(resolve => ws.addEventListener('open', resolve, { once: true }))
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (!message.id) { onEvent(message); return }
    const request = pending.get(message.id)
    if (!request) return
    pending.delete(message.id)
    clearTimeout(request.timer)
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result)
  })
  async function rpc(method, params = {}) {
    await ready
    return new Promise((resolve, reject) => {
      const id = ++seq
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)) }, 90000)
      pending.set(id, { resolve, reject, timer })
      ws.send(JSON.stringify({ id, method, params }))
    })
  }
  async function evaluate(expression) {
    const response = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
    return response.result?.value
  }
  return { rpc, evaluate, close: () => ws.close() }
}

let browser, main, sibling, siblingTarget
const requests = [], runtimeErrors = []
let interruptSM2 = true, injectedFailures = 0
const profile = mkdtempSync(join(tmpdir(), 'kms-demo-ui-'))
const readKeys = `(() => new Promise((resolve,reject) => {
  const request=indexedDB.open('kms-demo-node-keystore',4);
  request.onsuccess=()=>{const db=request.result;const tx=db.transaction('keys','readonly');const rows=tx.objectStore('keys').getAll();rows.onsuccess=()=>{const result=rows.result.map(row=>({nodeId:row.nodeId,keyRef:row.keyRef,algorithm:row.algorithm,keyId:row.keyId,version:row.version,publicKey:row.publicKey})).sort((a,b)=>a.keyRef.localeCompare(b.keyRef));tx.oncomplete=()=>{db.close();resolve(result)}};rows.onerror=()=>reject(rows.error)};
  request.onerror=()=>reject(request.error)
}))()`
async function waitFor(expression, label, timeout = 30000, client = main) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await client.evaluate(expression)) return
    await delay(150)
  }
  throw new Error(`Timed out: ${label}; ${await client.evaluate('document.body.innerText.slice(0,1400)')}`)
}
const hasText = text => `document.body.innerText.includes(${JSON.stringify(text)})`
async function navigate(path, origin = ORIGIN) {
  await main.rpc('Page.navigate', { url: `${origin}${BASE}${path}` })
}
async function click(text) {
  const clicked = await main.evaluate(`(() => {const button=[...document.querySelectorAll('button')].find(row=>row.innerText.trim()===${JSON.stringify(text)});if(!button||button.disabled)return false;button.click();return true})()`)
  if (!clicked) {
    const detail = await main.evaluate(`JSON.stringify({path:location.pathname,navbar:document.querySelector('.navbar')?.innerText,buttons:[...document.querySelectorAll('button')].map(b=>({text:b.innerText.trim(),disabled:b.disabled})),body:document.body.innerText.slice(0,1000)})`)
    assert(clicked, `enabled button exists: ${text}; ${detail}`)
  }
}
async function startInitialization() {
  // 锁竞争提示先出现，随后页面还会异步刷新对账状态；不能把提示出现
  // 当作按钮已恢复。像真实使用者一样等加载完成，再断言按钮可操作。
  await waitFor(`!![...document.querySelectorAll('.node-init__actions button')].find(button=>/开始初始化|继续初始化/.test(button.innerText)&&!button.disabled&&!button.classList.contains('is-loading'))`, 'initialization button ready')
  const clicked = await main.evaluate(`(() => {const button=[...document.querySelectorAll('.node-init__actions button')].find(row=>/开始初始化|继续初始化/.test(row.innerText));if(!button||button.disabled||button.classList.contains('is-loading'))return false;button.click();return true})()`)
  assert(clicked, 'initialization is an explicit enabled UI action')
}
async function api(path, { method = 'GET', body } = {}) {
  return main.evaluate(`(async()=>{
    const contextResponse=await fetch('/demo-api/lifecycle/demo/context',{credentials:'same-origin',signal:AbortSignal.timeout(15000)});
    const envelope=await contextResponse.json();
    if(envelope.code!==200)throw new Error('context unavailable: '+JSON.stringify(envelope));
    const context=envelope.data;
    const headers={'Content-Type':'application/json'};
    if(context.csrfToken&&Number.isInteger(context.revision)){headers['X-Kms-Demo-CSRF']=context.csrfToken;headers['X-Kms-Demo-Revision']=String(context.revision)}
    const response=await fetch(${JSON.stringify(`/demo-api${path}`)},{method:${JSON.stringify(method)},credentials:'same-origin',headers,signal:AbortSignal.timeout(30000),${body === undefined ? '' : `body:JSON.stringify(${JSON.stringify(body)}),`}});
    return {status:response.status,body:await response.json()};
  })()`)
}
async function serverSnapshot() {
  const data = requireOk(await api('/pqkds/node-self/keys/'), 'read current registered keys')
  return (data.keys || []).map(row => ({ algorithm: row.algorithm, keyId: row.keyId,
    keyVersion: row.keyVersion, publicKey: row.publicKey, allowsNewWork: row.allowsNewWork })).sort((a,b)=>a.algorithm.localeCompare(b.algorithm))
}
async function createNode(nodeId, index) {
  const result = await api('/pqkds/nodes/register/', { method: 'POST', body: {
    node_id: nodeId, name: nodeId, ip_address: `10.243.${20 + Math.floor(Math.random()*190)}.${index+1}`,
    port: 60000 + Math.floor(Math.random()*4000), permission_level: 'L2', domain_id: `demo-ui-${seed}`
  } })
  const data = requireOk(result, 'register owned UI fixture')
  assert(!data.is_duplicate, 'fixture ID must be new; never clean up an existing node')
  owned.push({ nodeId, id: data.id || data.node?.id })
  check(`${nodeId}: no activation credential returned`, !data.activation_code)
}

try {
  const available = await fetch(`${ORIGIN}/demo-api/lifecycle/demo/context`, { signal: AbortSignal.timeout(10000) })
  const availability = await available.json()
  assert(availability.code === 200 && availability.data?.enabled === true, 'Demo must be explicitly enabled before this test')
  browser = spawn(CHROME, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`,
    '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })
  let target
  for (let i=0; i<60 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find(row=>row.type==='page') }
    catch { /* Chrome startup */ }
    if (!target) await delay(100)
  }
  assert(target, 'browser started')
  main = connect(target.webSocketDebuggerUrl, message => {
    if (message.method === 'Runtime.exceptionThrown') runtimeErrors.push(message.params.exceptionDetails.text)
    if (message.method === 'Network.requestWillBeSent') {
      const request = message.params.request
      if (request.url.includes('/demo-api/')) requests.push({ url: request.url, method: request.method,
        headers: Object.fromEntries(Object.entries(request.headers).map(([key,value])=>[key.toLowerCase(),value])) })
    }
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params
      let interrupt = false
      if (interruptSM2 && request.method === 'POST' && new URL(request.url).pathname.endsWith('/node-self/keys/')) {
        try { interrupt = JSON.parse(request.postData).algorithm === 'SM2' } catch { /* not the selected registration */ }
      }
      if (interrupt) {
        interruptSM2 = false; injectedFailures++
        main.rpc('Fetch.fulfillRequest', { requestId, responseCode: 503,
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
          body: Buffer.from(JSON.stringify({ code: 503, msg: 'UI_TEST_INTERRUPTED_SM2_REGISTRATION' })).toString('base64') }).catch(error=>runtimeErrors.push(error.message))
      } else main.rpc('Fetch.continueRequest', { requestId }).catch(error=>runtimeErrors.push(error.message))
    }
  })
  await main.rpc('Runtime.enable'); await main.rpc('Page.enable'); await main.rpc('Network.enable')
  await main.rpc('Fetch.enable', { patterns: [{ urlPattern: '*/demo-api/pqkds/node-self/keys/*' }] })
  await navigate('/demo')
  await waitFor(hasText('缺少节点 ID'), 'explicit anonymous node entry')
  check('Demo has no password or activation form', await main.evaluate(`!document.querySelector('input[type=password]')`))
  await main.evaluate(`(async()=>{document.cookie='Admin-Token=demo-ui-standalone-sentinel;path=/';await new Promise((resolve,reject)=>{const r=indexedDB.open('kms-node-keystore',4);r.onupgradeneeded=()=>{for(const [name,keyPath]of [['meta','k'],['keys','keyRef'],['deviceKeys','keyRef'],['sessionKeys','sessionId']])r.result.createObjectStore(name,{keyPath})};r.onsuccess=()=>{const db=r.result;const tx=db.transaction('meta','readwrite');tx.objectStore('meta').put({k:'ui-test-sentinel',value:'standalone-untouched'});tx.oncomplete=()=>{db.close();resolve()}};r.onerror=()=>reject(r.error)})})()`)
  await click('管理控制台')
  await waitFor(`location.pathname.endsWith('/demo/admin/index')`, 'first opaque Demo admin session')
  check('Demo cookie is opaque HttpOnly while standalone cookie survives', await main.evaluate(`document.cookie.includes('Admin-Token=demo-ui-standalone-sentinel')&&!document.cookie.includes('KMS-Demo-Session=')`))
  const cookies = (await main.rpc('Network.getCookies', { urls: [ORIGIN] })).cookies
  const opaque = cookies.find(cookie=>cookie.name==='KMS-Demo-Session')
  check('actual Demo cookie is HttpOnly and opaque, not a JWT', opaque?.httpOnly&&opaque.value.length>=32&&!opaque.value.includes('.'))
  const admin = requireOk(await api('/lifecycle/demo/context'), 'real admin context')
  check('server authority is ADMIN without nodeId', admin.principalType === 'ADMIN' && !admin.nodeId)
  await createNode(nodeIds[0], 0); await createNode(nodeIds[1], 1)

  await navigate(`/demo?nodeId=${nodeIds[0]}`)
  await waitFor(`location.pathname.endsWith('/demo/node/initialize')&&${hasText(nodeIds[0])}&&!!document.querySelector('.node-init__actions button:not([disabled])')`, 'A pending-init UI')
  check('first entry does not silently generate keys', (await main.evaluate(readKeys)).length === 0)
  await startInitialization()
  await waitFor(`${hasText('UI_TEST_INTERRUPTED_SM2_REGISTRATION')}&&![...document.querySelectorAll('.node-init__actions button')].some(b=>b.classList.contains('is-loading'))`, 'deliberately interrupted registration', 180000)
  check('one registration was deliberately interrupted', injectedFailures === 1)
  const partial = (await main.evaluate(readKeys)).filter(row=>row.nodeId===nodeIds[0])
  check('failed registration retains generated material', partial.length === 3 && partial.some(row=>row.algorithm==='SM2'))

  // Hold the real per-mode/node lock from another actual tab without changing the authority revision.
  siblingTarget = (await main.rpc('Target.createTarget', { url: `${ORIGIN}${BASE}/demo/node/initialize` })).targetId
  let siblingInfo
  for (let i=0; i<50 && !siblingInfo; i++) {
    siblingInfo = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find(row=>row.id===siblingTarget)
    if (!siblingInfo) await delay(100)
  }
  assert(siblingInfo, 'second tab exists')
  sibling = connect(siblingInfo.webSocketDebuggerUrl)
  await sibling.rpc('Runtime.enable')
  await waitFor(hasText(nodeIds[0]), 'second pending-init tab', 30000, sibling)
  await sibling.evaluate(`(()=>{navigator.locks.request(${JSON.stringify(`kms-init/DEMO/${nodeIds[0]}`)},async()=>{window.__kmsInitLockHeld=true;await new Promise(resolve=>window.__kmsReleaseInitLock=resolve)});return true})()`)
  await waitFor('window.__kmsInitLockHeld===true', 'second tab owns browser lock', 10000, sibling)
  await startInitialization()
  await waitFor(hasText('另一标签页正在初始化'), 'competing initialization refuses generation')
  check('competing tab keeps all retained key refs', hash(await main.evaluate(readKeys)) === hash(partial))
  await sibling.evaluate('window.__kmsReleaseInitLock()')
  await main.rpc('Target.closeTarget', { targetId: siblingTarget }); sibling.close(); sibling = null; siblingTarget = null
  await startInitialization()
  await waitFor(hasText('初始化已完成'), 'resume A initialization', 180000)
  const aLocal = (await main.evaluate(readKeys)).filter(row=>row.nodeId===nodeIds[0])
  check('resume creates only missing Falcon and preserves prior refs', aLocal.length === 4 && partial.every(row=>aLocal.some(key=>hash(key)===hash(row))))
  const aServer = await serverSnapshot()
  check('four actual algorithms are registered and usable', aServer.length===4 && aServer.every(row=>row.allowsNewWork))
  await click('进入工作台')
  await waitFor(`location.pathname.endsWith('/demo/node/workbench')&&!!document.querySelector('.workbench-page')`, 'A shared workbench')
  await main.evaluate(`window.__demoUiBeforeReload = true`)
  await main.rpc('Page.reload')
  await waitFor(`window.__demoUiBeforeReload === undefined && document.readyState !== 'loading' && !!document.querySelector('.workbench-page')`, 'new document after workbench refresh reuses material')
  check('refresh preserves current IDs/versions/public keys and local rows', hash(await serverSnapshot())===hash(aServer) && hash((await main.evaluate(readKeys)).filter(row=>row.nodeId===nodeIds[0]))===hash(aLocal))

  await click('管理控制台')
  await waitFor(`location.pathname.endsWith('/demo/admin/index')`, 'A to admin full reload')
  const saved = requireOk(await api('/lifecycle/demo/context'), 'saved node context')
  check('admin server context retains A for return', saved.principalType==='ADMIN'&&saved.returnNodeId===nodeIds[0]&&!saved.nodeId)
  await click('返回节点工作台')
  await waitFor(`location.pathname.endsWith('/demo/node/workbench')&&!!document.querySelector('.workbench-page')`, 'restore A from admin')
  check('return uses saved server node rather than URL role', requireOk(await api('/lifecycle/demo/context'), 'restored context').nodeId===nodeIds[0])

  requireOk(await api('/pqkds/key-pool/'), 'Demo node pool metadata')
  requireOk(await api('/pqkds/key-pool/stats/'), 'Demo node pool statistics')
  await navigate('/demo/node/distzone/selfpool')
  await waitFor(`!!document.querySelector('.el-table') && !document.querySelector('button.is-loading')`, 'shared node pool page loaded')
  const poolView = await main.evaluate(`({error:document.body.innerText.includes('加载密钥池失败'),visibleMaintenance:[...document.querySelectorAll('button')].filter(button=>button.innerText.trim()==='生成并分发'&&button.getClientRects().length>0).map(button=>button.innerText.trim()),text:document.body.innerText.slice(0,1500)})`)
  check('shared Demo node pool page loads without administrative controls', !poolView.error && poolView.visibleMaintenance.length === 0, JSON.stringify(poolView))
  await click('预分配保护包')
  await waitFor(`location.pathname.endsWith('/demo/node/distzone/prealloc') && ${hasText('预分配')}`, 'existing local protection-package workflow')
  check('Demo pool action uses the existing local preallocation page', await main.evaluate(`!document.body.innerText.includes('404错误')`))

  await navigate(`/demo?nodeId=${nodeIds[1]}`)
  await waitFor(`location.pathname.endsWith('/demo/node/initialize')&&${hasText(nodeIds[1])}`, 'B pending-init UI')
  await waitFor(`!![...document.querySelectorAll('.node-init__actions button')].find(b=>b.innerText.includes('开始初始化')&&!b.disabled)`, 'B explicit initialize button')
  await startInitialization()
  await waitFor(hasText('初始化已完成'), 'B initialization', 180000)
  const bServer = await serverSnapshot()
  const both = await main.evaluate(readKeys)
  check('A/B private-material namespaces coexist without binding cleanup', both.filter(row=>row.nodeId===nodeIds[0]).length===4&&both.filter(row=>row.nodeId===nodeIds[1]).length===4)
  check('B cannot reuse A key IDs or public material', bServer.every(row=>!aServer.some(a=>a.keyId===row.keyId||a.publicKey===row.publicKey)))

  // Delete only the Demo DB in this newly-created test profile, with every prior connection unloaded.
  await navigate('/demo')
  await waitFor(hasText('缺少节点 ID'), 'unload IDB connections before missing-material test')
  await main.evaluate(`(()=>new Promise((resolve,reject)=>{const r=indexedDB.deleteDatabase('kms-demo-node-keystore');r.onsuccess=()=>resolve(true);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(new Error('test-owned Demo DB is still open in another tab'))}))()`)
  const writesBefore = requests.filter(row=>row.method==='POST'&&row.url.endsWith('/node-self/keys/')).length
  await navigate(`/demo?nodeId=${nodeIds[1]}`)
  await waitFor(hasText('密钥材料需恢复，已禁止自动初始化或覆盖'), 'ACTIVE missing-material recovery gate')
  check('missing material blocks auto-generation and initialization UI', await main.evaluate(`![...document.querySelectorAll('.node-init__actions button')].some(b=>/开始初始化|继续初始化|进入工作台/.test(b.innerText))`))
  check('missing-material entry leaves server keys unchanged', hash(await serverSnapshot())===hash(bServer))
  check('missing-material entry never submits new keys', writesBefore===requests.filter(row=>row.method==='POST'&&row.url.endsWith('/node-self/keys/')).length)
  check('Demo does not send legacy Authorization on real browser requests', requests.length>0&&requests.every(row=>!('authorization'in row.headers)))
  check('standalone token remains unchanged throughout Demo', await main.evaluate(`document.cookie.includes('Admin-Token=demo-ui-standalone-sentinel')`))
  await navigate('/standalone', STANDALONE)
  await waitFor(hasText('独立运行'), 'return to original standalone gateway')
  check('original 80 entry remains a separate standalone document', await main.evaluate(`location.origin===${JSON.stringify(STANDALONE)}&&!![...document.querySelectorAll('button')].find(b=>b.innerText==='节点登录')`))
  check('no uncaught application exceptions during real flow', runtimeErrors.length===0, runtimeErrors.join('; '))
  console.log(`Real Demo UI flow passed; ${requests.length} Demo requests observed; temporary profile ${profile}`)
} finally {
  if (main && owned.length) {
    try {
      await navigate('/demo')
      await waitFor(`location.origin===${JSON.stringify(ORIGIN)}&&${hasText('受控演示')}`, 'cleanup in original controlled origin')
      requireOk(await api('/lifecycle/demo/context/admin', { method:'POST',body:{} }), 'cleanup admin authority')
      const response = requireOk(await api('/pqkds/nodes/?page=1&limit=500'), 'cleanup owned node lookup')
      const rows = Array.isArray(response) ? response : response?.results || response?.data || []
      for (const record of owned) {
        const row = rows.find(node=>node.node_id===record.nodeId)
        if (!row || row.name!==record.nodeId || (record.id && Number(row.id)!==Number(record.id))) {
          console.warn(`[CLEANUP SKIP] fixture identity no longer matches ${record.nodeId}`)
          continue
        }
        requireOk(await api(`/pqkds/nodes/${row.id}/`, {method:'DELETE'}), `delete owned fixture ${record.nodeId}`)
        console.log(`[CLEANUP] deleted owned fixture ${record.nodeId}`)
      }
    } catch (error) { console.warn(`[CLEANUP FAILED] only owned fixtures may remain: ${owned.map(row=>row.nodeId).join(', ')}; ${error.message}`);process.exitCode=1 }
  }
  if (sibling) sibling.close()
  if (main) main.close()
  if (browser) browser.kill()
}
