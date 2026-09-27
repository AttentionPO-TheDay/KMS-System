// =============================================================================
// verify-manual-rotation.mjs —— 验证「手动密钥轮换 + 版本更迭展示」
// -----------------------------------------------------------------------------
// 背景（2026-09-24）：用户前台原来**没有**任何入口能触发真正的轮换 ——
// 更新弹窗只提交 名称/用途/所属域，而后端按"请求里有没有新 uA"分流，
// 于是"密钥更新"永远只改元数据：版本不变、链上没有新记录，
// 界面上更看不到"版本更迭"。
//
// 本次改动：更新弹窗加「重新生成本地密钥材料」（产生新 uA 并随请求提交）+
// 列表加「版本」列 + 详情加「版本更迭」轨迹表（数据来自 key_operation_record）。
//
// 验证方式：真实浏览器 + 数据库双证据，界面结论一律以库为准。
//
// 用法：node tools/verify-manual-rotation.mjs [keyId] [username] [password]
//
// ⚠️ 两个踩过的坑，写在这里省得下次再踩：
//   1) 必须用**密钥属主（普通用户）**登录：管理端与用户前台共用一个登录入口，
//      登录后守卫按角色分流，admin 会被直接送到 /updatedel/ 管理控制台，
//      根本进不到用户前台的更新与回收页（D9 单入口设计）。
//   2) 用户前台这个页面的真实路径是 **/user/lifecycle/index**（嵌套子路由），
//      只写 /user/lifecycle 时路由匹配不到子路由，主区域渲染为空 ——
//      现象是"页面标题栏在、内容全空"，很容易误判成功能坏了。
//   3) 表格列一律**按表头名定位**：第一列是勾选框，写死下标会整体错位。
// =============================================================================
import { execSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const KEY_ID = Number(process.argv[2] || 72)
const USERNAME = process.argv[3] || 'yx'
const PASSWORD = process.argv[4] || 'admin123'

const CDP_PORT = 9223
const ORIGIN = 'http://127.0.0.1'
const LIFECYCLE_URL = `${ORIGIN}/user/lifecycle/index`

const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find((p) => existsSync(p))
if (!CHROME) {
  console.error('找不到 Chrome/Edge')
  process.exit(1)
}

const results = []
function check(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`${pass ? '  [PASS]' : '  [FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const sql = (query) => execSync(
  `docker exec kms_mysql mysql -uroot -proot123456 -N -e "${query}" 2>nul`, { encoding: 'utf8' }
).trim()

let ws
let msgId = 0
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId
    const timer = setTimeout(() => reject(new Error(`timeout: ${method}`)), 60000)
    const onMessage = (ev) => {
      const msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString())
      if (msg.id === id) {
        clearTimeout(timer)
        ws.removeEventListener('message', onMessage)
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
      }
    }
    ws.addEventListener('message', onMessage)
    ws.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const { result, exceptionDetails } = await rpc('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true
  })
  if (exceptionDetails) throw new Error(exceptionDetails.text || 'JS 异常')
  return result?.value
}

// 按表头名定位：返回该密钥所在行（el-table 序号 + 行序号 + 各列下标）
//
// ⚠️ 必须以 `.el-table` **根元素**为单位定位，不能遍历 `<table>`：
//    Element Plus 把表头与表体渲染成两个独立的 <table>（有 fixed 列时表体还会再复制一份），
//    于是"同一张 <table> 里既有 thead 又有 tbody"这个假设不成立 ——
//    按 <table> 找会永远匹配不到（表头那张 0 行、表体那张没有 thead），
//    现象是定位返回 null，看起来像"数据没渲染"，其实是选择器错了。
const LOCATOR = (keyId) => `(() => {
  const roots = [...document.querySelectorAll('.el-table')]
  for (let ti = 0; ti < roots.length; ti++) {
    const headers = [...roots[ti].querySelectorAll('.el-table__header th')].map(th => th.innerText.trim())
    const idIdx = headers.indexOf('密钥 ID')
    if (idIdx < 0) continue
    const trs = [...roots[ti].querySelectorAll('.el-table__body tbody tr')]
    for (let ri = 0; ri < trs.length; ri++) {
      const tds = [...trs[ri].querySelectorAll('td')]
      if (tds[idIdx] && tds[idIdx].innerText.trim() === String(${keyId})) {
        return { ti, ri, idIdx, versionIdx: headers.indexOf('版本'), headers }
      }
    }
  }
  return null
})()`

const VERSION_CELL = `(() => {
  const loc = ${LOCATOR(KEY_ID)}
  if (!loc || loc.versionIdx < 0) return ''
  const roots = [...document.querySelectorAll('.el-table')]
  const tr = roots[loc.ti].querySelectorAll('.el-table__body tbody tr')[loc.ri]
  const tds = [...tr.querySelectorAll('td')]
  return tds[loc.versionIdx]?.innerText.trim() || ''
})()`

const CLICK_ROW_BUTTON = (label) => `(() => {
  const loc = ${LOCATOR(KEY_ID)}
  if (!loc) return false
  const roots = [...document.querySelectorAll('.el-table')]
  const tr = roots[loc.ti].querySelectorAll('.el-table__body tbody tr')[loc.ri]
  const btn = [...tr.querySelectorAll('button')].find(b => b.innerText.trim() === '${label}')
  if (!btn) return false
  btn.click()
  return true
})()`

const profileDir = mkdtempSync(join(tmpdir(), 'rotation-'))
const chrome = spawn(CHROME, [
  `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profileDir}`,
  '--headless=new', '--no-first-run', '--no-default-browser-check',
  '--window-size=1680,1000', 'about:blank'
], { stdio: 'ignore' })

try {
  let target = null
  for (let i = 0; i < 40 && !target; i++) {
    try {
      target = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((t) => t.type === 'page')
    } catch {}
    if (!target) await sleep(500)
  }
  if (!target) throw new Error('CDP 未就绪')

  ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true })
    ws.addEventListener('error', rej, { once: true })
  })
  await rpc('Runtime.enable')
  await rpc('Page.enable')

  console.log('\n=== 0. 基线（数据库）===')
  const before = sql(`select concat(version,'|',key_name,'|',user_name,'|',encryt_name) from kms.keymanage where key_id=${KEY_ID};`)
  const [beforeVersionRaw, keyName, owner, algo] = before.split('|')
  const beforeVersion = Number(beforeVersionRaw)
  console.log(`  keyId=${KEY_ID}  ${keyName} / ${owner} / ${algo}  当前版本=${beforeVersion}`)
  check('基线可取到密钥与版本', Boolean(before) && Number.isFinite(beforeVersion))

  console.log('\n=== 1. 登录并进入「更新与回收」===')
  const token = await login(ORIGIN, '/lifecycle-api', USERNAME, PASSWORD)
  check(`以密钥属主登录成功（${USERNAME}）`, Boolean(token))
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` })
  await sleep(2500)
  await evaluate(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await rpc('Page.navigate', { url: LIFECYCLE_URL })
  await sleep(8000)
  const tableInfo = await evaluate(`(() => {
    const tables = [...document.querySelectorAll('table')]
    return { count: tables.length, rows: tables.map(t => t.querySelectorAll('tbody tr').length) }
  })()`)
  check('更新与回收页渲染出数据表', tableInfo.count > 0 && tableInfo.rows.some((n) => n > 0),
    `${tableInfo.count} 张表 / 行数 ${JSON.stringify(tableInfo.rows)}`)

  console.log('\n=== 2. 「版本」列 ===')
  const locator = await evaluate(LOCATOR(KEY_ID))
  check('能按表头定位到该密钥所在行', Boolean(locator), locator ? `列: ${locator.headers.join('|')}` : '')
  check('列表存在「版本」列', locator?.versionIdx >= 0, locator ? `下标=${locator.versionIdx}` : '')
  const cellBefore = await evaluate(VERSION_CELL)
  check(`轮换前该行显示 v${beforeVersion}`, cellBefore === `v${beforeVersion}`, `实际="${cellBefore}"`)

  console.log('\n=== 3. 更新弹窗：生成本地新材料 ===')
  check('点击该密钥的「更新」', (await evaluate(CLICK_ROW_BUTTON('更新'))) === true)
  await sleep(2000)
  const clickedGen = await evaluate(`(() => {
    const b = [...document.querySelectorAll('.el-dialog button')].find(x => x.innerText.includes('重新生成本地密钥材料'))
    if (b) { b.click(); return true }
    return false
  })()`)
  check('弹窗里存在「重新生成本地密钥材料」按钮', clickedGen === true)
  await sleep(1500)
  const hint = (await evaluate(`[...document.querySelectorAll('.rotation-hint')].map(e => e.innerText).join(' ')`)).replace(/\s+/g, ' ')
  check(`提示出现版本更迭 ${beforeVersion} → ${beforeVersion + 1}`,
    new RegExp(`${beforeVersion}\\s*→\\s*${beforeVersion + 1}`).test(hint), hint.slice(0, 110))
  const ready = (await evaluate(`document.querySelector('.rotation-ready')?.innerText.trim() || ''`)).replace(/\s+/g, ' ')
  check('展示新本地材料（uA 摘要 + 生成时间）', /已生成/.test(ready), ready.slice(0, 80))

  console.log('\n=== 4. 提交轮换 ===')
  check('点击「确认更新」', (await evaluate(`(() => {
    const b = [...document.querySelectorAll('.el-dialog button')].find(x => x.innerText.trim() === '确认更新')
    if (b) { b.click(); return true }
    return false
  })()`)) === true)
  await sleep(11000)

  console.log('\n=== 5. 后端事实（以数据库为准）===')
  const afterRow = sql(`select concat(version,'|',chain_status) from kms.keymanage where key_id=${KEY_ID};`)
  const afterVersion = Number(afterRow.split('|')[0])
  check(`数据库 version +1（${beforeVersion} → ${beforeVersion + 1}）`, afterVersion === beforeVersion + 1, `实际=${afterRow}`)
  const records = sql(`select concat(key_version,'|',action_type,'|',action_source,'|',ifnull(chain_status,'-')) from kms.key_operation_record where key_id=${KEY_ID} order by record_id desc limit 3;`)
  check('落了一条 UPDATE 操作记录（版本更迭的数据源）', /UPDATE/.test(records), records.replace(/\n/g, ' / '))

  console.log('\n=== 6. 界面反映更迭 ===')
  await rpc('Page.navigate', { url: LIFECYCLE_URL })
  await sleep(8000)
  const cellAfter = await evaluate(VERSION_CELL)
  check(`列表该行更新为 v${beforeVersion + 1}`, cellAfter === `v${beforeVersion + 1}`, `实际="${cellAfter}"`)

  console.log('\n=== 7. 详情里的「版本更迭」轨迹 ===')
  check('点击该密钥的「详情」', (await evaluate(CLICK_ROW_BUTTON('详情'))) === true)
  await sleep(4500)
  const history = await evaluate(`(() => {
    const box = document.querySelector('.version-history')
    if (!box) return { ok: false, rows: [], text: '' }
    const rows = [...box.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
    return { ok: true, rows, text: box.innerText.replace(/\\s+/g, ' ').slice(0, 200) }
  })()`)
  check('详情里出现「版本更迭」区块', history.ok === true, history.text || '')
  check(`轨迹里能看到 v${beforeVersion + 1} 那一行`,
    (history.rows || []).some((r) => String(r[0]) === `v${beforeVersion + 1}`),
    JSON.stringify(history.rows || []).slice(0, 220))
  // 操作时间必须是页面统一的 YYYY-MM-DD HH:mm:ss，不能出现 ISO 的 `T` 与毫秒
  // （后端 action_time 是 ISO 串，直接渲染会与列表里的时间格式不一致）
  const timeCell = (history.rows || [])[0]?.[4] || ''
  check('轨迹的操作时间格式与页面一致（无 T / 毫秒）',
    /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(timeCell), `实际="${timeCell}"`)

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
