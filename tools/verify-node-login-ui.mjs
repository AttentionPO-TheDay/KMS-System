// =============================================================================
// verify-node-login-ui.mjs —— 走**界面**验证节点激活与免输入登录
// -----------------------------------------------------------------------------
// 与 verify-node-device-auth.mjs 的区别：
//   那个脚本在浏览器控制台里**直接调接口**（证明服务端链路对）；
//   本脚本**点界面**（证明用户真的走得通）—— 填表、点页签、点「已激活节点」。
//
// 全程真浏览器、真 WebCrypto、真 IndexedDB（节点的设备私钥真的落在里面）。
//
// 用法：node tools/verify-node-login-ui.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const API = '/lifecycle-api'
const PQKDS = '/pqkds-api'
const PORT = 9351
const NODE_ID = `Node-UI-${Date.now().toString(36).toUpperCase().slice(-5)}`
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function captcha(uuid) {
  const raw = execFileSync('docker', ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`], { encoding: 'utf8' }).trim()
  return raw ? raw.replace(/^"(.*)"$/s, '$1') : ''
}

const dir = mkdtempSync(join(tmpdir(), 'nodeui-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
/** 页面**自己**那次 /captchaImage 的 uuid。必须用它，不能另取一张 —— 见下。 */
let pageCaptchaUuid = ''
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e) => (await rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })).result?.value

// ⚠️ 必须抓**页面自己**那次 captchaImage 的响应拿 uuid。
//    自己再 fetch 一张是没用的：那张的验证码答案与 uuid 配成一对，
//    但表单提交时用的是**页面状态里**的 uuid（getCode() 写的），
//    两边不是同一张 → 服务端必然判"验证码错误"，
//    而那看起来和"密码错"很像，很容易误判成账号问题。
function hookCaptcha() {
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.method === 'Network.responseReceived' && /captchaImage/.test(m.params?.response?.url || '')) {
      rpc('Network.getResponseBody', { requestId: m.params.requestId })
        .then((r) => { try { pageCaptchaUuid = JSON.parse(r.body).uuid || '' } catch { /* 非 JSON */ } })
        .catch(() => { /* 响应体可能已被丢弃，忽略 */ })
    }
  })
}

/** 只取真正可输入的文本框（排除 el-radio-button 渲染出的 radio） */
const TEXT_INPUTS = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
const SET = `(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}`

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up */ }
    if (!t) await sleep(500)
  }
  if (!t) throw new Error('拿不到 CDP page target')
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable'); await rpc('Network.enable')
  hookCaptcha()

  // ---- 1. 管理员在界面上登录 ----
  console.log('\n== 1. 管理员登录（界面）==')
  pageCaptchaUuid = ''
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` }); await sleep(4000)
  check('捕获到页面自身的验证码 uuid', Boolean(pageCaptchaUuid), pageCaptchaUuid || '未捕获')
  await ev(`(() => { const set=${SET}; const ins=${TEXT_INPUTS}
    set(ins[0],'admin'); set(ins[1],'admin123'); set(ins[2],${JSON.stringify(captcha(pageCaptchaUuid))}); return true })()`)
  await sleep(500)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('登')); b.click(); return true })()`)
  await sleep(7000)
  const adminPath = await ev(`location.pathname`)
  check('管理员登录后进站', !adminPath.includes('/login'), adminPath)

  console.log(`\n== 2. 建节点 ${NODE_ID}（接口，拿凭证）==`)
  const adminToken = await ev(`document.cookie.match(/Admin-Token=([^;]+)/)?.[1] || ''`)
  // port 用随机值：服务端对 (ip, port) 有唯一约束，固定 0 会与既有节点撞车
  const reg = await ev(`fetch('${PQKDS}/nodes/register/',{method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer ${adminToken}'},
    body:JSON.stringify({node_id:${JSON.stringify(NODE_ID)},name:${JSON.stringify(NODE_ID)},
      ip_address:'127.0.0.1',port:${9000 + Math.floor(Math.random() * 900)},node_type:'validator',
      permission_level:'L2',domain_id:'domain-1'})}).then(r=>r.json())`)
  const code = reg?.data?.activation_code || ''
  check('建节点并拿到激活凭证', Boolean(code), code ? `长度 ${code.length}` : reg?.msg)

  // ---- 3. 在**界面上**完成节点激活 ----
  console.log('\n== 3. 节点激活（界面：切页签 + 填表 + 点按钮）==')
  // 清掉管理员会话，回到登录页 —— 模拟"节点操作者打开这台电脑"
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` }); await sleep(3500)

  const tabbed = await ev(`(() => {
    const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点')
    if(!b) return false
    b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(800)
  check('切到「节点」页签', tabbed === true)

  const emptyHint = await ev(`document.querySelector('.activated-empty')?.innerText || ''`)
  check('未激活时提示去激活', emptyHint.includes('还没有已激活的节点'), emptyHint.slice(0, 30).replace(/\s+/g, ' '))

  // 节点模式下：第 1 个文本框是节点名，第 2 个是激活凭证（无密码/无验证码）
  const nodeFieldCount = await ev(`(() => { const ins=${TEXT_INPUTS}; return {n:ins.length, ph:ins.map(i=>i.placeholder)} })()`)
  check('节点模式只有「节点名 + 凭证」两个输入框', nodeFieldCount.n === 2, JSON.stringify(nodeFieldCount.ph))

  await ev(`(() => { const set=${SET}; const ins=${TEXT_INPUTS}
    set(ins[0],${JSON.stringify(NODE_ID)}); set(ins[1],${JSON.stringify(code)}); return true })()`)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活')); b.click(); return true })()`)
  await sleep(8000)
  const afterActivate = await ev(`location.pathname`)
  check('激活后进站（应落到 /node-init 引导页）',
    !afterActivate.includes('/login') && afterActivate.includes('node-init'), afterActivate)

  // ---- 4. 本机真的存下了设备私钥 ----
  console.log('\n== 4. 设备凭据落在本机 IndexedDB ==')
  const stored = await ev(`(async () => {
    const db = await new Promise((res,rej)=>{const r=indexedDB.open('kms-node-keystore');r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})
    if(!db.objectStoreNames.contains('deviceKeys')) return {exists:false, stores:[...db.objectStoreNames]}
    const rows = await new Promise((res,rej)=>{const tx=db.transaction('deviceKeys','readonly');const q=tx.objectStore('deviceKeys').getAll();q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)})
    const mine = rows.find(r=>r.keyRef==='node-${NODE_ID}-device-auth')
    return {exists:!!mine, count:rows.length, keyRefs:rows.map(r=>r.keyRef),
            privateIsCryptoKey: mine ? (mine.privateKey && mine.privateKey.type==='private') : null}
  })()`)
  check('deviceKeys store 存在', stored?.exists === true, JSON.stringify(stored?.keyRefs || stored?.stores))
  check('存的是 CryptoKey 私钥对象（非字节）', stored?.privateIsCryptoKey === true)

  // ---- 5. 退出后用「已激活节点」免输入登录 ----
  console.log('\n== 5. 免输入登录（点已激活节点）==')
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` }); await sleep(3500)
  await ev(`(() => {
    const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点')
    b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(1200)

  const listed = await ev(`[...document.querySelectorAll('.activated-name')].map(e=>e.innerText.trim())`)
  check('登录页列出了已激活节点', Array.isArray(listed) && listed.includes(NODE_ID), JSON.stringify(listed))

  await ev(`(() => { const b=[...document.querySelectorAll('.activated-item')].find(x=>x.innerText.includes(${JSON.stringify(NODE_ID)})); if(!b) return false; b.click(); return true })()`)
  await sleep(7000)
  const afterQuick = await ev(`location.pathname`)
  check('点击后免输入登录成功', !afterQuick.includes('/login'), afterQuick)

  // ---- 6. 反例：清掉本机私钥后，该节点应从列表消失 ----
  console.log('\n== 6. 反例：清本机私钥后不再列出 ==')
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await ev(`(async () => {
    const db = await new Promise((res)=>{const r=indexedDB.open('kms-node-keystore');r.onsuccess=()=>res(r.result)})
    await new Promise((res)=>{const tx=db.transaction('deviceKeys','readwrite');tx.objectStore('deviceKeys').delete('node-${NODE_ID}-device-auth');tx.oncomplete=res})
    return true })()`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` }); await sleep(3500)
  await ev(`(() => {
    const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点')
    b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(1200)
  const listedAfter = await ev(`[...document.querySelectorAll('.activated-name')].map(e=>e.innerText.trim())`)
  check('清掉私钥后该节点不再出现在列表', !listedAfter.includes(NODE_ID), JSON.stringify(listedAfter))
  const emptyAfter = await ev(`document.querySelector('.activated-empty')?.innerText || ''`)
  check('回落到"去激活"提示', emptyAfter.includes('还没有已激活的节点'), emptyAfter.slice(0, 24).replace(/\s+/g, ' '))

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.p)
  console.log(`总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  process.exitCode = failed.length ? 1 : 0
} catch (e) {
  console.error('\n[ERROR]', e.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}
