// =============================================================================
// verify-workbench-shape.mjs —— 节点工作台的两个**硬性数字**
// -----------------------------------------------------------------------------
// 计划 §3.6.5：**KPI 卡片必须仍是 4 张、图表必须仍是 5 张**，
// 这是用户明确要求保留的，任何重构都不得减少。
//
// ⚠️ 2026-10-08 修：本脚本原先作用于 `/user/workbench` —— 那是阶段 1 就已
//    合并下线的前台（nginx 对 `/user/` 显式 404）。也就是说它**一直是坏的**：
//    打开一个 404 页，DOM 里当然什么都没有，报"KPI 为 0 张"。
//    一条恒失败的检查比没有检查更糟 —— 它会让人以为"工作台坏了"，
//    或者干脆被无视，从而在真正的回归发生时没有任何提醒。
//    现在改成：**节点令牌 → 真工作台（/updatedel/workbench）**，
//    并自带浏览器（与其它验收脚本一致，不再要求外部先起一个 9222）。
//
// 判据同时校验**内容**而不只是数量：把标题取出来打印，
// 免得出现"数量对但内容错"（例如 4 张卡片全是别的东西）。
//
// 用法：node tools/verify-workbench-shape.mjs
// =============================================================================
import { spawn, execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const DOMAIN = 'wb-shape'
const PORT = 9401
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const dir = mkdtempSync(join(tmpdir(), 'wbshape-'))
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
  if (r?.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || '页面求值异常')
  return r?.result?.value
}

const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')

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

  // 工作台对 PENDING_INIT 的节点是打不开的（守卫送回引导页），
  // 所以这里必须用一个**已初始化**的节点 —— 与真实使用路径一致。
  const created = await lib.createNode(admin, { prefix: 'WS', domainId: DOMAIN })
  const session = await lib.activateNode(created.nodeId, created.activationCode)
  const cryptoProvider = lib.cryptoProvider
  for (const [algo, opts] of [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]) {
    const kp = await cryptoProvider.generate(algo, { nodeId: created.nodeId, ...opts })
    await fetch(`${ORIGIN}/pqkds-api/pqkds/node-self/keys/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.token}` },
      body: JSON.stringify({
        algorithm: algo, publicKey: kp.publicKey, deviceId: session.fingerprint,
        keyId: kp.keyId, keyVersion: kp.version
      })
    })
  }
  await fetch(`${ORIGIN}/pqkds-api/pqkds/node-self/init/`, {
    method: 'POST', headers: { Authorization: `Bearer ${session.token}` }
  })

  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3000)
  await ev(`document.cookie='Admin-Token=${session.token}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/workbench` })
  await sleep(9000)

  const shape = await ev(`(() => {
    // KPI 卡片与图表容器都按类名统计；同时把标题取出来，便于人工确认不是"数量对但内容错"
    const kpi = [...document.querySelectorAll('.kpi-card, .stat-card, .summary-card')]
    const boxes = [...document.querySelectorAll('.chart-box')]
    const sections = [...document.querySelectorAll('.section-card .section-head span:first-child')].map(s => s.innerText.trim())
    return {
      path: location.pathname,
      kpiCount: kpi.length,
      kpiTitles: kpi.map(e => e.innerText.split('\\n').map(s=>s.trim()).filter(Boolean)[0]).filter(Boolean),
      chartBoxCount: boxes.length,
      chartTitles: sections,
      canvasCount: document.querySelectorAll('canvas').length
    }
  })()`)

  console.log('工作台结构：')
  console.log('  实际路径          =', shape.path)
  console.log('  KPI 卡片数        =', shape.kpiCount, '  期望 4')
  console.log('  KPI 标题          =', JSON.stringify(shape.kpiTitles))
  console.log('  .chart-box 容器数 =', shape.chartBoxCount, '  期望 5')
  console.log('  区块标题          =', JSON.stringify(shape.chartTitles))
  console.log('  已渲染 canvas 数  =', shape.canvasCount)

  const onWorkbench = String(shape.path || '').includes('workbench')
  const kpiOk = shape.kpiCount === 4
  const chartOk = shape.chartBoxCount === 5
  console.log('')
  console.log(onWorkbench ? '  [OK]   真的落在工作台页' : `  [FAIL] 落在了 ${shape.path}（不是工作台）`)
  console.log(kpiOk ? '  [OK]   KPI 仍为 4 张' : `  [FAIL] KPI 为 ${shape.kpiCount} 张，应为 4 张`)
  console.log(chartOk ? '  [OK]   图表仍为 5 张' : `  [FAIL] 图表为 ${shape.chartBoxCount} 张，应为 5 张`)

  process.exitCode = (onWorkbench && kpiOk && chartOk) ? 0 : 1
} catch (e) {
  console.error('[ERROR]', e.message)
  process.exitCode = 1
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
}
