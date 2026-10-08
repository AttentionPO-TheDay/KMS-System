// =============================================================================
// verify-login-remembered-node.mjs —— 「这台设备记住哪个节点」的登录页行为
// -----------------------------------------------------------------------------
// 钉住四条，每一条都有明确的失败形态：
//
//   1. **免密优先**：本机已有可免密登录的节点时，登录页默认只显示那个节点，
//      **收起**激活表单。失败形态：用户每次都以为得填一遍凭证。
//   2. **一键换节点**：此时有一个按钮可以展开表单去登新节点；
//      展开后说清"会替换掉本机的登录信息"（**一台设备一个节点**，不是多存一份）。
//   3. **陈旧记录清理**：服务端已经没有那个节点（被删/库被重置）时，
//      登录页把它从"已激活节点"里清掉 —— 连本机设备凭据与绑定文件一起清。
//      失败形态：留着一个点进去必然失败的条目，用户既看不出也删不掉。
//   4. **探测失败时绝不清理**（最重要的一条）：网络抖动或后端没有这条路由时，
//      必须**原样保留**本机记录 —— 私钥不可导出，误删等于毁掉唯一能登录的身份。
//
// ⚠️ 会真建节点、真走界面激活、真删节点，结尾自清。
// 用法：node tools/verify-login-remembered-node.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const DOMAIN = 'login-recall'
const PORT = 9399
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const results = []
const check = (n, p, d = '') => { results.push({ n, p }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let ws, id = 0
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e) => {
  const r = await rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })
  return r?.exceptionDetails ? undefined : r?.result?.value
}
const SET = `(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}`

const dir = mkdtempSync(join(tmpdir(), 'loginrecall-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })
const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')

/** 打开登录页并切到「节点」页签（页面每次加载都会重新校对本机记录）。 */
async function openLoginNodeTab(waitMs = 6000) {
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(4000)
  await ev(`(() => {
    const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点')
    if(!b) return false; b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(waitMs)
}

/** 页面当前形态：列表 / 表单 / 按钮。 */
const pageShape = () => ev(`(() => ({
  listed: [...document.querySelectorAll('.activated-name')].map(e=>e.innerText.trim()),
  formVisible: [...document.querySelectorAll('.login-form input')].some(i=>(i.placeholder||'').includes('节点名称')),
  switchBtn: [...document.querySelectorAll('button')].some(b=>(b.innerText||'').trim()==='登录其它节点'),
  contextShown: Boolean(document.querySelector('.form-context')),
}))()`)

const localRecords = () => ev(`(async () => {
  const db = await new Promise((res)=>{const r=indexedDB.open('kms-node-keystore');r.onsuccess=()=>res(r.result)})
  const keys = await new Promise((res)=>{const tx=db.transaction('deviceKeys','readonly');const q=tx.objectStore('deviceKeys').getAll();q.onsuccess=()=>res(q.result.map(r=>String(r.keyRef||'')))})
  const meta = await new Promise((res)=>{const tx=db.transaction('meta','readonly');const q=tx.objectStore('meta').getAll();q.onsuccess=()=>res(q.result.filter(r=>String(r.k||'').endsWith('-binding')).map(r=>String(r.nodeId||'')))})
  return { deviceKeys: keys, bindings: meta }
})()`)

const deleteNode = (nodeId) => execFileSync('docker', ['exec', '-i', 'dvadmin3-django', 'python', '-'], {
  input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
rows = list(Node.objects.filter(node_id='${nodeId}'))
Node.objects.filter(pk__in=[n.pk for n in rows]).delete()
print('deleted=%d' % len(rows))
`,
  encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})

/** 在界面里激活一个节点（切页签 → 填节点名/凭证 → 必要时点换节点确认）。 */
async function activateViaUi(nodeId, code) {
  await openLoginNodeTab(2500)
  // 已有已激活节点时表单是收起的，先展开（这正是本次新增的按钮）。
  const shape = await pageShape()
  if (!shape.formVisible) {
    await ev(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='登录其它节点'); if(b) b.click(); return true })()`)
    await sleep(800)
  }
  await ev(`(() => { const set=${SET};
    const ins=[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]
    set(ins[0],${JSON.stringify(nodeId)}); set(ins[1],${JSON.stringify(code)}); return true })()`)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活')); if(!b) return false; b.click(); return true })()`)
  await sleep(2000)
  // 换节点确认框（本机已有别的绑定）
  await ev(`(() => { const b=[...document.querySelectorAll('.node-switch-confirm button')].find(x=>/清除旧绑定并登录|确定/.test(x.innerText)); if(b) b.click(); return true })()`)
  await sleep(8000)
  return String(await ev(`location.pathname`) || '')
}

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

  // ===== 1. 无任何记录时：必须显示表单（否则无路可走）=====
  console.log('\n== 1. 本机没有任何节点时 ==')
  await openLoginNodeTab()
  const emptyShape = await pageShape()
  check('★ 没有已激活节点时**显示表单**（否则用户无路可走）',
    emptyShape?.formVisible === true && (emptyShape?.listed || []).length === 0,
    JSON.stringify(emptyShape))

  // ===== 2. 激活第一个节点后：免密优先、表单收起 =====
  console.log('\n== 2. 激活节点后（界面）==')
  const n1 = await lib.createNode(admin, { prefix: 'LR1', domainId: DOMAIN })
  const n2 = await lib.createNode(admin, { prefix: 'LR2', domainId: DOMAIN })
  const path1 = await activateViaUi(n1.nodeId, n1.activationCode)
  check('在界面里激活成功（落到节点首次初始化页）', path1.includes('node-init'), path1)

  await openLoginNodeTab()
  const shape1 = await pageShape()
  check('★★ 有已激活节点时**只显示免密登录**、表单收起',
    (shape1?.listed || []).includes(n1.nodeId) && shape1?.formVisible === false,
    JSON.stringify(shape1))
  check('★★ 此时给出「登录其它节点」按钮',
    shape1?.switchBtn === true, `switchBtn=${shape1?.switchBtn}`)

  // 点按钮 → 表单展开，且说清"会替换本机登录信息"
  await ev(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='登录其它节点'); if(b) b.click(); return true })()`)
  await sleep(900)
  const expanded = await pageShape()
  check('★ 点按钮后表单展开，并说明会替换本机登录信息（一台设备一个节点）',
    expanded?.formVisible === true && expanded?.contextShown === true,
    JSON.stringify(expanded))
  check('★ 表单展开后按钮消失（不留"点了没反应"的装饰）',
    expanded?.switchBtn === false, `switchBtn=${expanded?.switchBtn}`)

  // ===== 3. 激活第二个节点 → 第一个被替换（一台设备一个节点）=====
  console.log('\n== 3. 换节点后本机只留新的那个 ==')
  const path2 = await activateViaUi(n2.nodeId, n2.activationCode)
  check('第二个节点也在界面里激活成功', path2.includes('node-init'), path2)
  const local2 = await localRecords()
  check('★★ 本机设备凭据与绑定文件**只剩新的那个**（旧的被清掉）',
    (local2?.deviceKeys || []).some((k) => k.includes(n2.nodeId))
    && !(local2?.deviceKeys || []).some((k) => k.includes(n1.nodeId))
    && (local2?.bindings || []).includes(n2.nodeId)
    && !(local2?.bindings || []).includes(n1.nodeId),
    `deviceKeys=${JSON.stringify(local2?.deviceKeys)} bindings=${JSON.stringify(local2?.bindings)}`)

  // ===== 4. 服务端删掉它 → 登录页清掉本机记录 =====
  console.log('\n== 4. 服务端已不存在时（库被重置/节点被删）==')
  deleteNode(n2.nodeId)
  await openLoginNodeTab(7000)
  const shape3 = await pageShape()
  const local3 = await localRecords()
  check('★★ 陈旧节点**不再出现在**「已激活节点」里',
    !(shape3?.listed || []).includes(n2.nodeId), JSON.stringify(shape3?.listed))
  check('★★ 它的设备凭据与绑定文件也一并清掉（不是只在界面上藏起来）',
    !(local3?.deviceKeys || []).some((k) => k.includes(n2.nodeId))
    && !(local3?.bindings || []).includes(n2.nodeId),
    `deviceKeys=${JSON.stringify(local3?.deviceKeys)} bindings=${JSON.stringify(local3?.bindings)}`)
  check('★ 清空后回到"显示表单"的默认形态（否则用户什么都点不了）',
    shape3?.formVisible === true, JSON.stringify(shape3))

  // ===== 5. ★ 探测失败时**绝不清理** =====
  // 再造一个：激活 → 服务端删除 → **屏蔽探测接口** → 刷新。
  // 此时"存在性"无从判断，本机记录必须原样保留。
  console.log('\n== 5. 探测不可用时不许清理（安全兜底）==')
  const n3 = await lib.createNode(admin, { prefix: 'LR3', domainId: DOMAIN })
  await activateViaUi(n3.nodeId, n3.activationCode)
  const beforeBlock = await localRecords()
  check('第三个节点已在本机留下记录（作为兜底判据的靶子）',
    (beforeBlock?.bindings || []).includes(n3.nodeId), JSON.stringify(beforeBlock?.bindings))

  deleteNode(n3.nodeId) // 服务端没有了
  await rpc('Network.setBlockedURLs', { urls: ['*still-exists*'] }) // 探测打不出去
  await openLoginNodeTab(7000)
  const blockedShape = await pageShape()
  const blockedLocal = await localRecords()
  check('★★★ 探测失败时本机记录**原样保留**（宁可留着点不动的条目，也不误删唯一能用的身份）',
    (blockedLocal?.bindings || []).includes(n3.nodeId)
    && (blockedLocal?.deviceKeys || []).some((k) => k.includes(n3.nodeId)),
    `bindings=${JSON.stringify(blockedLocal?.bindings)} 列表=${JSON.stringify(blockedShape?.listed)}`)

  // 放开屏蔽 → 同一页面刷新后应把它清掉（证明第 4 节的行为不是偶然）
  await rpc('Network.setBlockedURLs', { urls: [] })
  await openLoginNodeTab(7000)
  const freedLocal = await localRecords()
  check('★ 探测恢复后同一记录被清掉（对照：说明第 5 节保留是因为探测失败，不是逻辑没跑）',
    !(freedLocal?.bindings || []).includes(n3.nodeId),
    `bindings=${JSON.stringify(freedLocal?.bindings)}`)
} catch (e) {
  console.error('\n[ERROR]', e.message)
  results.push({ n: '脚本异常', p: false })
} finally {
  try {
    await rpc('Network.setBlockedURLs', { urls: [] }).catch(() => {})
  } catch { /* noop */ }
  try {
    execFileSync('docker', ['exec', '-i', 'dvadmin3-django', 'python', '-'], {
      input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
rows = list(Node.objects.filter(domain_id='${DOMAIN}' ))
Node.objects.filter(pk__in=[n.pk for n in rows]).delete()
print('left=%d' % Node.objects.filter(domain_id='${DOMAIN}').count())
`,
      encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    })
  } catch { /* noop */ }
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
  const failed = results.filter((r) => !r.p).length
  console.log(`\n===== 汇总 =====\n总计 ${results.length}，通过 ${results.length - failed}，失败 ${failed}`)
  results.filter((r) => !r.p).forEach((r) => console.log(`  - ${r.n}`))
  process.exitCode = failed ? 1 : 0
}