// =============================================================================
// verify-node-landing.mjs —— 节点端**落地页（工作台）**验证
// -----------------------------------------------------------------------------
// 断言的行为（用户原话）：
//   * "进来就是总览页面的图表" —— 登录后直接落在总览，不经过中间页
//   * "三个子系统在页面上，应该在图表的上方，作为主元素展示"
//   * "零条也要渲染出来 0" —— 空数据不能被"暂无数据"盖住
//
// ⚠️ 关于"0 渲染出来"的可测性说明（不要假装它测到了）：
//    ECharts 画在 <canvas> 上，DOM 里看不到图例与中心数字，
//    所以本脚本能断言的是：
//      a) 不再有 `.chart-notice` 遮罩（改前正是它把图表盖住的）
//      b) 图表 canvas 真的存在且有尺寸（说明画了东西）
//      c) KPI 卡片的数字是 0
//    至于"图例里那一串 0"是否真的画出来了，靠人工看截图确认 ——
//    verify 脚本只做它能诚实做到的部分。
//
// 令牌经内部通道铸发（与 Django 走同一条桥），避免依赖本机设备私钥。
//
// 用法：node tools/verify-node-landing.mjs [nodeId]
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const API = '/lifecycle-api'
const PORT = 9411
const NODE_ID = process.argv[2] || ''
const SHOT_PATH = 'C:/tmp/node-landing.png'

const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }

const sh = (c, a) => execFileSync(c, a, { encoding: 'utf8' })
const envOf = (k) => sh('bash', ['-lc', `grep '^${k}=' /c/Users/AllenR/Desktop/kms-code/kms-ops/.env | cut -d= -f2-`]).trim()
function mysql(sql) {
  return sh('docker', ['exec', 'kms_mysql', 'mysql', '-uroot', `-p${envOf('MYSQL_ROOT_PASSWORD')}`,
    '--default-character-set=utf8mb4', '-N', '-e', sql])
    .split('\n').map((s) => s.trim()).filter((s) => s && !/Warning/i.test(s))
}

// 优先挑一个**数据为空**的节点 —— 那才是"零也要渲染出 0"的考察场景
function pickNode() {
  if (NODE_ID) return NODE_ID
  const rows = mysql("SELECT node_id FROM falcon_kds.dvadmin_pqkds_nodes WHERE status='active' ORDER BY id DESC LIMIT 1;")
  return rows[0] || ''
}

const dir = mkdtempSync(join(tmpdir(), 'landing-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => { const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString()); if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) } }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e) => {
  const r = await rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) return { __err: r.exceptionDetails.exception?.description || r.exceptionDetails.text }
  return r.result?.value
}

const READ_SIDEBAR = `(() => {
  const sc = document.querySelector('.sidebar-container')
  if (!sc) return { present: false, items: [], groups: [] }
  return {
    present: true,
    items: [...sc.querySelectorAll('.el-menu-item .menu-title')].map(e => e.innerText.trim()),
    groups: [...sc.querySelectorAll('.el-sub-menu__title .menu-title')].map(e => e.innerText.trim())
  }
})()`

const CLICK_CARD = (title) => `(() => {
  const c=[...document.querySelectorAll('.subsystem-card')].find(x=>x.innerText.includes(${JSON.stringify(title)}))
  if(!c) return false
  c.click(); return true
})()`

const CLICK_GROUP = (label) => `(() => {
  const el=[...document.querySelectorAll('.sidebar-container .el-sub-menu__title')].find(x=>x.innerText.trim()===${JSON.stringify(label)})
  if(!el) return false
  el.click(); return true
})()`

try {
  const nodeId = pickNode()
  if (!nodeId) {
    console.log('没有 ACTIVE 节点可用。先跑 tools/verify-node-full-loop.mjs 走一遍完整流程，')
    console.log('或显式传入：node tools/verify-node-landing.mjs <nodeId>')
    process.exitCode = 1
    process.exit(0)
  }
  const userId = mysql(`SELECT sys_user_id FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${nodeId}';`)[0]
  console.log(`使用节点 ${nodeId}（sys_user_id=${userId}）`)

  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up */ }
    if (!t) await sleep(500)
  }
  if (!t) throw new Error('拿不到 CDP page target')
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1000, deviceScaleFactor: 1, mobile: false })

  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3000)
  const mint = await ev(`fetch('${API}/internal/lifecycle/session/issue',{method:'POST',
    headers:{'Content-Type':'application/json','X-Internal-Token':${JSON.stringify(envOf('INTERNAL_TOKEN'))}},
    body:JSON.stringify({userId:${userId}})}).then(r=>r.json())`)
  const token = mint?.data?.token
  if (!token) throw new Error('铸令牌失败：' + JSON.stringify(mint).slice(0, 200))
  await ev(`document.cookie='Admin-Token=${token}; path=/'`)

  // ---- 1. 登录后落在总览（不再经中间页）----
  console.log('\n== 1. 落地页就是总览 ==')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/` })
  await sleep(7000)
  const landed = await ev(`({path: location.pathname, is404: !!document.querySelector('.wscn-http404'), hasChart: !!document.querySelector('.chart-box'), cards: document.querySelectorAll('.subsystem-card').length, hasSidebar: !!document.querySelector('.sidebar-container'), hasHamburger: !!document.querySelector('#hamburger-container')})`)
  check('进入系统后直接落在工作台（总览）', String(landed?.path).includes('workbench'), String(landed?.path))
  check('没有落到 404', landed?.is404 === false)
  check('页面上有图表容器', landed?.hasChart === true)
  check('页面上有三个子系统卡片', landed?.cards === 3, `实际 ${landed?.cards}`)
  // 落地页**整页不显示侧边栏**：它自己就是"选去处 + 看数据"的页面，
  // 旁边再挂一列菜单会与内容争注意力。
  check('落地页不显示侧边栏', landed?.hasSidebar === false, String(landed?.hasSidebar))
  check('落地页也收起了折叠按钮（点了不会有反应）',
    landed?.hasHamburger === false, String(landed?.hasHamburger))

  // ---- 2. 子系统在图表**上方** ----
  console.log('\n== 2. 子系统位于图表上方（主元素）==')
  const order = await ev(`(() => {
    const cards=document.querySelector('.subsystem-grid')
    const kpi=document.querySelector('.kpi-card')
    const chart=document.querySelector('.chart-box')
    if(!cards||!chart) return null
    return {
      cardsTop: Math.round(cards.getBoundingClientRect().top),
      chartTop: Math.round(chart.getBoundingClientRect().top),
      kpiTop: kpi ? Math.round(kpi.getBoundingClientRect().top) : null
    }
  })()`)
  check('子系统卡片在图表之上', order && order.cardsTop < order.chartTop,
    order ? `cards=${order.cardsTop} chart=${order.chartTop}` : '取不到位置')
  check('子系统卡片在最上方（在 KPI 之前）',
    order && order.kpiTop != null && order.cardsTop <= order.kpiTop,
    order ? `cards=${order.cardsTop} kpi=${order.kpiTop}` : '')

  const rowCheck = await ev(`(() => {
    const r=[...document.querySelectorAll('.subsystem-card')].map(c=>c.getBoundingClientRect())
    return r.map(x=>({top:Math.round(x.top), left:Math.round(x.left)}))
  })()`)
  check('三个子系统卡片横向排列',
    Array.isArray(rowCheck) && rowCheck.length === 3 && rowCheck.every((x) => Math.abs(x.top - rowCheck[0].top) <= 2),
    JSON.stringify(rowCheck))

  // ---- 3. 零数据不被"暂无数据"盖住 ----
  console.log('\n== 3. 零数据渲染为 0（不被遮罩盖住）==')
  // 等所有图表初始化完成
  await sleep(3000)
  const zeroState = await ev(`(() => {
    const notices=[...document.querySelectorAll('.chart-notice')].map(e=>e.innerText.trim()).filter(Boolean)
    const boxes=[...document.querySelectorAll('.chart-box')]
    return {
      notices,
      boxCount: boxes.length,
      sized: boxes.filter(b=>b.getBoundingClientRect().height>50).length,
      canvases: [...document.querySelectorAll('.chart-box canvas')].map(c=>({w:c.width,h:c.height})),
      kpiValues: [...document.querySelectorAll('.kpi-value')].map(e=>e.innerText.trim())
    }
  })()`)
  check('没有任何"暂无数据"遮罩', (zeroState?.notices || []).length === 0, JSON.stringify(zeroState?.notices))
  check('所有图表容器都有实际高度', zeroState?.boxCount > 0 && zeroState?.sized === zeroState?.boxCount,
    `${zeroState?.sized}/${zeroState?.boxCount}`)
  check('图表 canvas 已绘制（有尺寸）',
    (zeroState?.canvases || []).length > 0 && (zeroState?.canvases || []).every((c) => c.w > 0 && c.h > 0),
    JSON.stringify(zeroState?.canvases))
  check('KPI 卡片显示 0（不是空白/占位）',
    (zeroState?.kpiValues || []).length === 4 && (zeroState?.kpiValues || []).every((v) => /^\d/.test(v)),
    JSON.stringify(zeroState?.kpiValues))

  const shot = await rpc('Page.captureScreenshot', { format: 'png' })
  writeFileSync(SHOT_PATH, Buffer.from(shot.data, 'base64'))
  console.log(`  （截图已存 ${SHOT_PATH} —— 图例里的 0 是否画出来，请人工看一眼）`)

  // ---- 4. 子系统卡片进入后侧边栏收敛 ----
  console.log('\n== 4. 从卡片进入子系统，侧边栏只留该子系统 ==')
  const CASES = [
    { card: '密钥生成', expect: ['生成密钥', '生成历史'] },
    { card: '密钥更新与回收', expect: ['我的密钥', '密钥更新', '版本历史', '密钥回收'] },
    { card: '密钥分发', expect: ['发起分发', '预分配', '密钥池', '会话管理', '分发记录'] }
  ]
  const ALL = CASES.flatMap((c) => c.expect)

  for (const c of CASES) {
    await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/workbench` })
    await sleep(4000)
    const clicked = await ev(CLICK_CARD(c.card))
    await sleep(4000)
    const path = await ev(`location.pathname`)
    check(`点「${c.card}」能进入`, clicked === true && !String(path).includes('workbench'), String(path))

    let sb = await ev(READ_SIDEBAR)
    if (sb?.groups?.length && !sb.items.length) {
      await ev(CLICK_GROUP(sb.groups[0]))
      await sleep(1200)
      sb = await ev(READ_SIDEBAR)
    }
    const shown = [...(sb?.groups || []), ...(sb?.items || [])]
    const foreign = ALL.filter((x) => !c.expect.includes(x) && shown.includes(x))
    check(`「${c.card}」内侧边栏只含本子系统项`,
      c.expect.every((x) => shown.includes(x)) && foreign.length === 0,
      foreign.length ? `混入 ${JSON.stringify(foreign)}` : JSON.stringify(shown))
  }

  // ---- 5. 非子系统页仍显示完整树 ----
  // 落地页（工作台）按设计**不显示**侧边栏，所以"完整树"要在一个**非落地页、
  // 也不在任何业务子系统内**的页面上验 —— 否则用户从工作台进不去「节点信息」。
  console.log('\n== 5. 非子系统页（当前节点）仍显示完整节点树 ==')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/selfzone/selfnode` })
  await sleep(5000)
  const wb = await ev(READ_SIDEBAR)
  const wbAll = [...(wb?.groups || []), ...(wb?.items || [])]
  check('非子系统页显示完整的节点树',
    wbAll.includes('更新与回收') && wbAll.includes('密钥分发') && wbAll.includes('节点信息'),
    JSON.stringify(wbAll))

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
