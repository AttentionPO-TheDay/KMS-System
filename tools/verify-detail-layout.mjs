// =============================================================================
// verify-detail-layout.mjs —— 详情面（el-descriptions）不横向溢出
// -----------------------------------------------------------------------------
// 用户报过：「查看密钥详情的时候…右侧多出一部分完全透明的表格只有黑色边框」。
//
// 根因（已定位并修复，见 assets/styles/element-ui.scss 里那段注释）：
//   Element Plus 的 `.el-descriptions__table` 只有 `width:100%`、**没有**
//   `table-layout: fixed`，表格用 auto 布局时列宽由"最小内容宽度"决定，
//   而本系统的详情里几乎处处是 64 位公钥摘要 / 32 位设备指纹 / tx 哈希这类
//   **没有空格的长 token** —— 一个 64 字符十六进制串在 13px 下约 466px 宽，
//   于是整张表被撑到容器外（实测两列 1000px+ vs 弹窗 780px）：
//   标签列被压到 37px（出现竖排的"版 本""公 钥 摘 要"），撑出去的那部分
//   只画边框、没有内容 —— 就是那块"透明的黑框"。
//
// 修法：全局给 `.el-descriptions__content` 加 `overflow-wrap: anywhere`
// （只有它**同时**允许断行**并**参与最小内容宽度计算；`break-word` 不改变
//  最小内容宽度，表格照样被撑出去）。
//
// 本脚本把"不溢出"变成可量的判据：**表宽 ≤ 容器宽**，且描述表内没有元素
// scrollWidth 超过 clientWidth。覆盖五处详情面（含用户报的那一处）。
//
// ⚠️ 判据只查**描述表**，不查数据表格：数据表格多列时本来就横向滚动
//    （容器带 --scrollable-x）、单元格刻意用 show-overflow-tooltip 截断，
//    那些是设计如此。把它们算进来会让这条检查**恒红**，而一条恒红的检查
//    等于没有检查（本仓在 verify-workbench-shape 上吃过这个亏）。
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const DOMAIN = 'layout-verify'
const PORT = 9405
const OUT = 'C:/tmp/shots'
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const results = []
const check = (n, p, d = '') => { results.push({ n, p }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const dir = mkdtempSync(join(tmpdir(), 'layout-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

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
const shot = async (name) => {
  const r = await rpc('Page.captureScreenshot', { format: 'png' })
  mkdirSync(OUT, { recursive: true })
  writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, 'base64'))
}

/** 量当前页面每一张 el-descriptions：表宽 vs 容器宽 + 描述表内的溢出元素。
 *  ⚠️ 这段是模板字符串：注释里**不要写反引号**，否则会提前闭合它
 *     （踩过一次 —— 报的是 "table is not defined"，看着像逻辑错）。 */
const measure = () => ev(`(() => {
  const tables = [...document.querySelectorAll('.el-descriptions__table')]
  return {
    count: tables.length,
    items: tables.map(t => {
      const box = t.parentElement
      const tw = Math.round(t.getBoundingClientRect().width)
      const bw = box ? Math.round(box.getBoundingClientRect().width) : null
      return { tableW: tw, boxW: bw, overflows: bw != null && tw > bw + 2 }
    }),
    tooWide: [...document.querySelectorAll('.el-descriptions *')]
      .filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2)
      .slice(0, 6)
      .map(el => ({ cls: String(el.className || '').slice(0, 50), sw: el.scrollWidth, cw: el.clientWidth }))
  }
})()`)

const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')

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

  // 靶子节点：必须有四套长期密钥（详情里的公钥摘要/指纹才够长，够长才测得出来）
  const created = await lib.createNode(admin, { prefix: 'DL', domainId: DOMAIN })
  const session = await lib.activateNode(created.nodeId, created.activationCode)
  for (const [algo, opts] of [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]) {
    const kp = await lib.cryptoProvider.generate(algo, { nodeId: created.nodeId, ...opts })
    await fetch(`${ORIGIN}/pqkds-api/pqkds/node-self/keys/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.token}` },
      body: JSON.stringify({ algorithm: algo, publicKey: kp.publicKey, deviceId: session.fingerprint,
        keyId: kp.keyId, keyVersion: kp.version })
    })
  }
  await fetch(`${ORIGIN}/pqkds-api/pqkds/node-self/init/`, { method: 'POST', headers: { Authorization: `Bearer ${session.token}` } })

  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(2500)
  await ev(`document.cookie='Admin-Token=${session.token}; path=/'`)

  // ---- 1. 密钥详情弹窗（用户报的那一处）----
  console.log('\n== 1. 密钥详情弹窗（用户报的那一处）==')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/genzone/history` })
  await sleep(8000)
  await ev(`(() => { const row=[...document.querySelectorAll('.el-table__row')][0]
    const b=row && [...row.querySelectorAll('button')].find(x=>/详情/.test(x.innerText)); if(b) b.click(); return true })()`)
  await sleep(3000)
  const m1 = await measure()
  check('★★ 密钥详情：描述表不超出容器（表宽 ≤ 容器宽）',
    (m1?.items || []).length > 0 && (m1?.items || []).every((i) => !i.overflows), JSON.stringify(m1?.items))
  check('★★ 密钥详情：描述表内没有横向溢出元素（那块"透明黑框"的判据）',
    (m1?.tooWide || []).length === 0, JSON.stringify(m1?.tooWide))
  await shot('30-keydetail')
  await ev(`(() => { const b=[...document.querySelectorAll('.el-dialog__footer button')].find(x=>/关/.test(x.innerText)); if(b) b.click(); return true })()`)
  await sleep(800)

  // ---- 2~4. 其余含描述表的节点侧页面 ----
  for (const [label, path] of [
    ['当前节点', '/selfzone/selfnode'],
    ['本地密钥环境', '/selfzone/keystore'],
    ['节点授权', '/distzone/selfauth']
  ]) {
    console.log(`\n== ${label} ==`)
    await rpc('Page.navigate', { url: `${ORIGIN}${BASE}${path}` })
    await sleep(6500)
    const m = await measure()
    check(`★ ${label}：描述表不超出容器`, (m?.items || []).every((i) => !i.overflows), JSON.stringify(m?.items))
    check(`★ ${label}：无横向溢出`, (m?.tooWide || []).length === 0, JSON.stringify(m?.tooWide))
  }

  // ---- 5. 管理端节点管理的「密钥」弹窗 ----
  console.log('\n== 5. 管理端「密钥」弹窗 ==')
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(2500)
  await ev(`document.cookie='Admin-Token=${admin}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/nodegov/nodes` })
  await sleep(7000)
  await ev(`(() => { const row=[...document.querySelectorAll('.el-table__row')][0]
    const b=row && [...row.querySelectorAll('button')].find(x=>x.innerText.trim()==='密钥'); if(b) b.click(); return true })()`)
  await sleep(3000)
  const m5 = await measure()
  check('★ 管理端密钥弹窗：描述表不超出容器', (m5?.items || []).every((i) => !i.overflows), JSON.stringify(m5?.items))
  check('★ 管理端密钥弹窗：无横向溢出', (m5?.tooWide || []).length === 0, JSON.stringify(m5?.tooWide))
} catch (e) {
  console.error('[ERROR]', e.stack || e.message)
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
print('cleaned left=%d' % Node.objects.filter(domain_id='${DOMAIN}').count())
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
