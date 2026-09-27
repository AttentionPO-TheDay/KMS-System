import { captchaFields } from './lib/captcha.mjs'
/**
 * 校验用户工作台的两个硬性约束（计划 §3.6.5）：
 *   - KPI 卡片必须仍是 4 张
 *   - 图表必须仍是 5 张
 * 这两个数字是用户明确要求保留的，任何重构都不得减少。
 *
 * 用法: node tools/verify-workbench-shape.mjs [cdpPort]
 */
const port = process.argv[2] || '9222'
const CDP = `http://127.0.0.1:${port}`
const ORIGIN = 'http://127.0.0.1'

let target
try {
  target = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json()
} catch {
  target = await (await fetch(`${CDP}/json/new?about:blank`)).json()
}
if (!target?.webSocketDebuggerUrl) throw new Error('无法新建 CDP 标签页')

const ws = new WebSocket(target.webSocketDebuggerUrl)
let msgId = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id)
    pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  }
})
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const i = ++msgId
    pending.set(i, { resolve: res, reject: rej })
    ws.send(JSON.stringify({ id: i, method, params }))
  })
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Network.setCacheDisabled', { cacheDisabled: true })
const evalJs = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' :: ' + (r.exceptionDetails.exception?.description || ''))
  return r.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

await send('Page.navigate', { url: `${ORIGIN}/user/login` })
await sleep(3000)
const ok = await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'yx', password:'admin123', ...${JSON.stringify(await captchaFields(ORIGIN))} }) })
  const j = await res.json()
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/'
  return !!j.token
})()`)
if (!ok) throw new Error('登录失败')

await send('Page.navigate', { url: `${ORIGIN}/user/workbench` })
await sleep(9000)

const shape = await evalJs(`(() => {
  // KPI 卡片与图表容器都按类名统计；同时把标题取出来，便于人工确认不是"数量对但内容错"
  const kpi = [...document.querySelectorAll('.kpi-card, .stat-card, .summary-card')]
  const boxes = [...document.querySelectorAll('.chart-box')]
  const sections = [...document.querySelectorAll('.section-card .section-head span:first-child')].map(s => s.innerText.trim())
  const cards = [...document.querySelectorAll('.kpi-grid > *, .kpi-row > *')].map(e => e.innerText.split('\\n')[0].trim())
  return JSON.stringify({
    kpiCount: kpi.length,
    kpiTitles: kpi.map(e => e.innerText.split('\\n').map(s=>s.trim()).filter(Boolean)[0]).filter(Boolean),
    chartBoxCount: boxes.length,
    chartTitles: sections,
    canvasCount: document.querySelectorAll('canvas').length,
    fallbackCards: cards
  })
})()`)

const s = JSON.parse(shape)
console.log('工作台结构：')
console.log('  KPI 卡片数        =', s.kpiCount, '  期望 4')
console.log('  KPI 标题          =', JSON.stringify(s.kpiTitles))
console.log('  .chart-box 容器数 =', s.chartBoxCount, '  期望 5')
console.log('  区块标题          =', JSON.stringify(s.chartTitles))
console.log('  已渲染 canvas 数  =', s.canvasCount)
if (s.fallbackCards.length) console.log('  兜底选择器命中    =', JSON.stringify(s.fallbackCards))

const kpiOk = s.kpiCount === 4
const chartOk = s.chartBoxCount === 5
console.log('')
console.log(kpiOk ? '  [OK]   KPI 仍为 4 张' : `  [FAIL] KPI 为 ${s.kpiCount} 张，应为 4 张`)
console.log(chartOk ? '  [OK]   图表仍为 5 张' : `  [FAIL] 图表为 ${s.chartBoxCount} 张，应为 5 张`)

ws.close()
process.exit(kpiOk && chartOk ? 0 : 1)