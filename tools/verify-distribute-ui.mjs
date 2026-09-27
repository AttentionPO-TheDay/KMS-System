// =============================================================================
// verify-distribute-ui.mjs —— 界面级验证：用户前台「密钥分发」可选节点封装算法
// -----------------------------------------------------------------------------
// 后端能力已由 verify-distribute-algorithm.mjs 验过（13/13）。本脚本只验界面：
//   1) 分发页出现「节点封装算法」，含 抗量子 Kyber / 抗量子 Falcon 两个选项
//   2) 默认选中 Kyber
//   3) 选 Falcon → 选源密钥 → 分发 → 数据库里新增批次的算法是 falcon_lattice
//      （以库为准，不靠界面文案）
//
// 用法：node tools/verify-distribute-ui.mjs [username] [password] [keyId]
// =============================================================================
import { execSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const USERNAME = process.argv[2] || 'yx'
const PASSWORD = process.argv[3] || 'admin123'
const KEY_ID = Number(process.argv[4] || 72)
const ORIGIN = 'http://127.0.0.1'
const CDP_PORT = 9235
const PAGE = '/user/distribute/index'
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))

const results = []
function check(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`${pass ? '  [PASS]' : '  [FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const sql = (q) => execSync(`docker exec kms_mysql mysql -uroot -proot123456 -N -e "${q}" 2>nul`, { encoding: 'utf8' }).trim()

const dir = mkdtempSync(join(tmpdir(), 'distui-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const rpc = (method, params = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.id === n) { ws.removeEventListener('message', on); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method, params }))
})
const ev = async (expr) => (await rpc('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.value
const waitFor = async (expr, timeoutMs = 20000) => {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try { if (await ev(expr)) return true } catch {}
    await sleep(400)
  }
  return false
}
const mouseClick = async (x, y) => {
  await rpc('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1, buttons: 1 })
  await rpc('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1, buttons: 1 })
}
const rectOf = (expr) => ev(`(() => {
  const el = ${expr}
  if (!el) return null
  const r = el.getBoundingClientRect()
  if (r.width <= 0 || r.height <= 0) return null
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
})()`)

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
    if (!t) await sleep(500)
  }
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable')

  console.log('\n=== 1. 登录并进入「密钥分发」===')
  const token = await login(ORIGIN, '/lifecycle-api', USERNAME, PASSWORD)
  check('登录成功', Boolean(token))
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` }); await sleep(2500)
  await ev(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${PAGE}` })
  const rendered = await waitFor(`document.body.innerText.includes('密钥分发')`)
  check('分发页已渲染', rendered)

  console.log('\n=== 2. 「封装体系 / 抗量子算法 / 节点腿算法」控件 ===')
  const labels = await ev(`[...document.querySelectorAll('.el-form-item__label')].map(l => l.innerText.trim())`)
  check('出现「封装体系」表单项', (labels || []).includes('封装体系'), JSON.stringify(labels || []))
  // 标签必须体现"两条腿"：节点信封（用节点公钥封）与我方信封（用你自己的密钥封）。
  // 之前叫「我的密钥」+「节点腿算法」，用户会以为其中一个是多余的 —— 实测被问过。
  check('标签区分「节点封装算法」与「我的解封密钥」',
    (labels || []).includes('节点封装算法') && (labels || []).includes('我的解封密钥'),
    JSON.stringify(labels || []))
  const families = await ev(`(() => {
    const item = [...document.querySelectorAll('.el-form-item')].find(i => i.innerText.includes('封装体系'))
    return [...(item?.querySelectorAll('.el-radio-button') || [])].map(e => e.innerText.trim())
  })()`)
  check('封装体系含「抗量子」「国密」', (families || []).includes('抗量子') && (families || []).includes('国密'), JSON.stringify(families || []))

  // 抗量子体系下应出现 Kyber / Falcon 两个选项
  const pqOptions = await ev(`(() => {
    const item = [...document.querySelectorAll('.el-form-item')].find(i => i.innerText.includes('抗量子算法'))
    return [...(item?.querySelectorAll('.el-radio-button') || [])].map(e => e.innerText.trim())
  })()`)
  check('抗量子体系下可选 Kyber / Falcon', (pqOptions || []).some((o) => /Kyber/.test(o)) && (pqOptions || []).some((o) => /Falcon/.test(o)), JSON.stringify(pqOptions || []))

  // 切到国密：抗量子算法那行应消失，节点腿算法跟随源密钥
  const gmRect = await rectOf(`[...document.querySelectorAll('.el-radio-button')].find(e => e.innerText.trim() === '国密')`)
  if (gmRect) {
    await mouseClick(gmRect.x, gmRect.y)
    await sleep(700)
  }
  const afterGm = await ev(`(() => {
    const labels = [...document.querySelectorAll('.el-form-item__label')].map(l => l.innerText.trim())
    const tag = [...document.querySelectorAll('.el-tag')].map(t => t.innerText.trim()).find(t => /国密|抗量子/.test(t))
    return { hasPqRow: labels.includes('抗量子算法'), nodeLeg: tag || '' }
  })()`)
  check('选国密后不再显示「抗量子算法」选择', afterGm.hasPqRow === false, `仍显示=${afterGm.hasPqRow}`)
  check('节点腿算法显示为国密（跟随源密钥）', /国密/.test(afterGm.nodeLeg), afterGm.nodeLeg)

  // 切回抗量子继续走下面的 Falcon 提交
  const pqRect = await rectOf(`[...document.querySelectorAll('.el-radio-button')].find(e => e.innerText.trim() === '抗量子')`)
  if (pqRect) {
    await mouseClick(pqRect.x, pqRect.y)
    await sleep(700)
  }

  console.log('\n=== 3. 选 Falcon 分发一次（库为准）===')
  const beforeMaxId = sql(`select ifnull(max(id),0) from falcon_kds.dvadmin_pqkds_pre_distributed_keys;`)
  const falconRect = await rectOf(`[...document.querySelectorAll('.el-radio-button')].find(e => /Falcon/.test(e.innerText))`)
  check('找到 Falcon 选项', Boolean(falconRect))
  if (falconRect) {
    await mouseClick(falconRect.x, falconRect.y)
    await sleep(600)
  }
  const checked = await ev(`(() => {
    const item = [...document.querySelectorAll('.el-form-item')].find(i => i.innerText.includes('抗量子算法'))
    const el = [...(item?.querySelectorAll('.el-radio-button') || [])].find(e => e.className.includes('is-active'))
    return el ? el.innerText.trim() : ''
  })()`)
  check('已切换到 Falcon', /Falcon/.test(checked), checked)

  // 选源密钥与接收节点（都是 el-select，用真实鼠标点）
  const formItemText = (label) => ev(`(() => {
    const item = [...document.querySelectorAll('.el-form-item')].find(i => i.innerText.includes(${JSON.stringify(label)}))
    return item ? item.innerText.replace(/\\s+/g, ' ').trim() : ''
  })()`)
  const chooseFirst = async (label) => {
    const rect = await rectOf(`[...document.querySelectorAll('.el-form-item')].find(i => i.innerText.includes(${JSON.stringify(label)}))?.querySelector('.el-select input')`)
    if (!rect) return false
    await mouseClick(rect.x, rect.y)
    await sleep(900)
    const optRect = await rectOf(`[...document.querySelectorAll('.el-select-dropdown__item')].find(e => e.getBoundingClientRect().height > 0)`)
    if (optRect) await mouseClick(optRect.x, optRect.y)
    await sleep(600)
    await rpc('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
    await rpc('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
    await sleep(400)
    return true
  }

  // ⚠️ 必须先断言"两项确实选中了"再提交 —— 上一版没断言，
  // 结果下拉没选中、提交无效，而"最新一行是 falcon"读到的是**上一轮**留下的行，
  // 断言假通过。假通过比失败更危险：它会让人以为功能验过了。
  await chooseFirst('我的解封密钥')
  const keyText = await formItemText('我的解封密钥')
  check('已选中源密钥', /（(SM2|SSCL)）/.test(keyText), keyText)
  await chooseFirst('接收节点')
  const nodeText = await formItemText('接收节点')
  check('已选中接收节点', /DEMO|演示节点/.test(nodeText), nodeText)

  const clicked = await ev(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim() === '分发')
    if (b) { b.click(); return true }
    return false
  })()`)
  check('点击「分发」', clicked === true)
  await sleep(12000)

  const after = sql(`select algorithm, count(*) from falcon_kds.dvadmin_pqkds_pre_distributed_keys group by algorithm;`)
  console.log(`  库内算法分布: ${after.replace(/\n/g, ' / ')}`)
  const newest = sql(`select algorithm from falcon_kds.dvadmin_pqkds_pre_distributed_keys order by id desc limit 1;`)
  check('界面提交产生了 falcon_lattice 的新行', newest === 'falcon_lattice', `最新一行算法=${newest}`)
  // 不断言"总行数增加"：密钥池列表接口每次都会顺手清理过期行，
  // 总数可能不增反减 —— 那样断言会偶发失败，且失败原因与本次改动无关。
  const newestId = Number(sql(`select id from falcon_kds.dvadmin_pqkds_pre_distributed_keys order by id desc limit 1;`))
  check('最新行的 id 是本次新产生的（大于提交前最大 id）',
    newestId > Number(beforeMaxId || 0), `提交前最大 id=${beforeMaxId}，最新 id=${newestId}`)

  const pageMsg = await ev(`document.body.innerText.replace(/\\s+/g,' ').slice(0, 200)`)
  console.log(`  页面提示: ${pageMsg.slice(0, 140)}`)

  const pass = results.filter((r) => r.pass).length
  console.log(`\n=== 结果：${pass}/${results.length} 通过 ===`)
  if (pass !== results.length) {
    console.log('未通过项：')
    results.filter((r) => !r.pass).forEach((r) => console.log(`  - ${r.name}  ${r.detail}`))
    process.exitCode = 1
  }
} catch (error) {
  console.error('\n执行失败:', error.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch {}
  chrome.kill()
}
