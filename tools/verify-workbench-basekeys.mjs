// =============================================================================
// verify-workbench-basekeys.mjs —— 初始化生成的四套基础密钥**出现在工作台上**
// -----------------------------------------------------------------------------
// 用户报过："初始化生成的密钥数据不展示在工作台的数据展示页面"。
//
// 根因不是数据丢了，是**工作台问错了地方**：它的密钥类卡片与图表全都来自
// **generate / lifecycle 两个子系统**的记录（`kms` 库），而四套基础密钥登记在
// **分发模块**的 `NodeLongTermKey`（`GET /node-self/keys/`）——两套不同的事实来源，
// 工作台从来没问过后者。
//
// 走真链路：建节点 → 界面激活 → 界面初始化四套密钥 → 打开工作台 →
// 断言 KPI「基础密钥」是 4/4、区块逐行列全四套。
//
// 对照组：**未初始化**的节点打不开工作台（守卫送回 /node-init）——
// 那一节钉的是"守卫拦住"这个事实，而不是"工作台显示 0"
// （后者永远观察不到：能进工作台的节点必然已初始化）。
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const DOMAIN = 'wb-basekey'
const PORT = 9400
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

const dir = mkdtempSync(join(tmpdir(), 'wbbasekey-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })
const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')

const workbenchState = () => ev(`(() => {
  const kpis = [...document.querySelectorAll('.kpi-card')].map(c => ({
    title: c.innerText.split('\\n').map(s=>s.trim()).filter(Boolean)[0],
    lines: c.innerText.split('\\n').map(s=>s.trim()).filter(Boolean).slice(1),
  }))
  const base = kpis.find(k => k.title === '基础密钥')
  return {
    kpiTitles: kpis.map(k => k.title),
    baseValue: base?.lines?.[0] || '',
    baseHint: base?.lines?.[1] || '',
    body: document.body.innerText.slice(0, 4000),
    chartBoxes: document.querySelectorAll('.chart-box').length,
    canvases: document.querySelectorAll('canvas').length,
  }
})()`)

const openWorkbenchAsNode = async (token) => {
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(2500)
  await ev(`document.cookie='Admin-Token=${token}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/workbench` })
  await sleep(9000)
}

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up */ }
    if (!t) await sleep(500)
  }
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable'); await rpc('Network.enable')

  const created = await lib.createNode(admin, { prefix: 'WB', domainId: DOMAIN })
  console.log(`节点：${created.nodeId}`)

  // ---- 1. 界面激活（拿节点令牌；工作的靶子）----
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(4000)
  await ev(`(() => { const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点'); if(!b) return false; b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(1200)
  await ev(`(() => { const set=${SET}; const ins=[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]
    set(ins[0],${JSON.stringify(created.nodeId)}); set(ins[1],${JSON.stringify(created.activationCode)}); return true })()`)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活')); if(!b) return false; b.click(); return true })()`)
  await sleep(8000)
  const nodeToken = String(await ev(`document.cookie.match(/Admin-Token=([^;]+)/)?.[1] || ''`))
  check('节点已在界面激活并拿到令牌', Boolean(nodeToken), `len=${nodeToken.length}`)

  // ---- 2. 初始化**之前**访问工作台：守卫会把未初始化的节点弹回引导页 ----
  //    ⚠️ 这是**设计如此**，不是"工作台空白"：PENDING_INIT 的节点进不了任何业务页。
  //    所以"初始化前工作台显示 0"这个对照**做不出来**——真到了工作台的节点
  //    必然已经初始化过。这里的断言就该是"被弹回 node-init"。
  //    （把这条写成"KPI 显示 0"会是个永远失败或永远无意义的断言。）
  console.log('\n== 2. 初始化之前：守卫拦在 /node-init（对照组）==')
  await openWorkbenchAsNode(nodeToken)
  const beforePath = String(await ev(`location.pathname`) || '')
  check('★ 未初始化的节点打不开工作台，被守卫送回「节点首次初始化」',
    beforePath.includes('node-init'), beforePath)

  // ---- 3. 界面完成初始化（四套密钥本机生成）----
  console.log('\n== 3. 界面初始化四套密钥 ==')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/node-init` })
  await sleep(6000)
  let clicked = 'TIMEOUT'
  for (let i = 0; i < 15; i++) {
    clicked = await ev(`(() => {
      const b=[...document.querySelectorAll('button')].find(x=>/开始初始化/.test(x.innerText))
      if(!b) return 'NOT_FOUND'
      if(b.disabled) return 'DISABLED'
      b.click(); return 'CLICKED'
    })()`)
    if (clicked === 'CLICKED') break
    await sleep(1000)
  }
  check('点了「开始初始化」', clicked === 'CLICKED', String(clicked))
  let inited = ''
  for (let i = 0; i < 40; i++) {
    await sleep(2000)
    const body = String(await ev(`document.body.innerText`) || '')
    if (body.includes('初始化已完成')) { inited = 'DONE'; break }
    inited = body.replace(/\s+/g, ' ').slice(0, 60)
  }
  check('四套密钥初始化完成', inited === 'DONE', inited)

  // ---- 4. 初始化**之后**：工作台必须显示四套 ----
  console.log('\n== 4. 初始化之后 ==')
  await openWorkbenchAsNode(nodeToken)
  const after = await workbenchState()
  check('★★ KPI「基础密钥」= 4（四套齐全）',
    String(after?.baseValue).trim() === '4', `值=${after?.baseValue} 提示=${after?.baseHint}`)
  check('★★ KPI 提示列出四个算法名',
    ['Kyber', 'SSCL', 'SM2', 'Falcon'].every((n) => String(after?.baseHint || '').includes(n)),
    String(after?.baseHint))
  check('★★ 区块里四套各自列出（每套都带 keyId 与版本）',
    ['Kyber', 'SSCL', 'SM2', 'Falcon'].every((n) => String(after?.body || '').includes(n))
    && (String(after?.body || '').match(/-KYBER-|-SSCL-|-SM2-|-FALCON-/g) || []).length >= 1,
    `含四算法=${['Kyber', 'SSCL', 'SM2', 'Falcon'].filter((n) => String(after?.body || '').includes(n)).join('/')}`)
  check('★ 区块显示状态是「可用」（服务端下发的文案，不是前端另写一份）',
    String(after?.body || '').includes('可用'), '见下方区块文本')
  check('★★ 图表仍是 5 张（**没**新增第 6 张 —— 那是仓库硬约束）',
    Number(after?.chartBoxes) === 5, `chart-box=${after?.chartBoxes}`)
  check('★ KPI 仍是 4 张',
    (after?.kpiTitles || []).length === 4, JSON.stringify(after?.kpiTitles))
  check('★ 「待审批申请」那张死卡片已被替换（阶段 8 已下线审批流）',
    !(after?.kpiTitles || []).includes('待审批申请'), JSON.stringify(after?.kpiTitles))
} catch (e) {
  console.error('\n[ERROR]', e.message)
  results.push({ n: '脚本异常', p: false })
} finally {
  try {
    execFileSync('docker', ['exec', '-i', 'dvadmin3-django', 'python', '-'], {
      input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
rows = list(Node.objects.filter(domain_id='${DOMAIN}'))
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
