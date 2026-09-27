// =============================================================================
// verify-falcon-pool.mjs —— 验证「密钥池支持 Falcon 格密码封装」
// -----------------------------------------------------------------------------
// 背景（2026-09-26）：密钥池页的「生成并分发」对话框此前只调
// `/key-pool/distribute/`，而那条路在服务端**写死 Kyber**（用发送方公钥封装），
// 于是密钥池的算法列永远只有 Kyber KEM —— 抗量子只剩一半，界面上无路可走。
//
// 本次改动：对话框加「封装算法」选择；选 Falcon 时改走 `/key-pool/generate/`
// （该接口按 algorithm 分流，用**接收方**的 Falcon 公钥封装）。
//
// 本脚本在真实浏览器里：打开密钥池页 → 打开对话框 → 断言两个算法选项都在
// → 选 Falcon → 提交 → 断言列表里出现 Falcon 行（且批次号是 falcon 池）。
//
// 前置：接收方节点必须已有 Falcon 公钥，否则服务端会明确报错
// （这也正是我们要断言的第二条路径）。
//
// 用法：node tools/verify-falcon-pool.mjs [senderNodeId] [receiverNodeId]
// =============================================================================
import { execSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const SENDER = process.argv[2] || 'DEMO-NODE-01'
const RECEIVER = process.argv[3] || 'DEMO-NODE-02'
const ORIGIN = 'http://127.0.0.1'
const CDP_PORT = 9232
const PAGE = '/updatedel/distchain/keypool'
const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find((p) => existsSync(p))

const results = []
function check(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`${pass ? '  [PASS]' : '  [FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const dir = mkdtempSync(join(tmpdir(), 'falconpool-'))
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

// 轮询等待条件成立 —— 别用固定 sleep：密钥池数据一多，页面渲染就慢，
// 固定等待会让下拉"打不开"（实测间歇性失败），而真正的原因是**还没渲染完**。
const waitFor = async (expr, timeoutMs = 15000, intervalMs = 400) => {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      if (await ev(expr)) return true
    } catch {}
    await sleep(intervalMs)
  }
  return false
}

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
    if (!t) await sleep(500)
  }
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable')

  console.log('\n=== 1. 以管理员登录并进入密钥池页 ===')
  const token = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
  check('管理员登录成功', Boolean(token))
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` }); await sleep(2500)
  await ev(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${PAGE}` })
  let tableReady = await waitFor(`document.querySelectorAll('.el-table__body tbody tr').length > 0`, 20000)
  if (!tableReady) {
    // 首次导航偶尔落在 SPA 初始化过程中（表格迟迟不渲染）——重载一次再来
    await rpc('Page.navigate', { url: `${ORIGIN}${PAGE}` })
    tableReady = await waitFor(`document.querySelectorAll('.el-table__body tbody tr').length > 0`, 25000)
  }
  check('密钥池表格已渲染', tableReady)

  // 基线在**表格渲染之后**取，且与第 5 步读的是同一份页面状态 ——
  // 否则"新增批次"的判断会拿旧页面当基线，出现假通过。
  const readBatches = () => ev(`(() => {
    const root = [...document.querySelectorAll('.el-table')].find(t => t.querySelector('.el-table__header'))
    const headers = [...(root?.querySelectorAll('.el-table__header th') || [])].map(th => th.innerText.trim())
    const bIdx = headers.indexOf('批次号')
    return [...(root?.querySelectorAll('.el-table__body tbody tr') || [])]
      .map(tr => [...tr.querySelectorAll('td')][bIdx]?.innerText.trim()).filter(Boolean)
  })()`)
  const batchesBefore = await readBatches()
  console.log(`  提交前已有批次（去重）: ${JSON.stringify([...new Set(batchesBefore || [])])}`)
  const pageText = (await ev(`document.body.innerText.replace(/\\s+/g,' ').slice(0,300)`)) || ''
  check('已进入密钥池页', /密钥池/.test(pageText), pageText.slice(0, 70))

  console.log('\n=== 2. 打开「生成并分发」对话框 ===')
  const opened = await ev(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim().includes('生成并分发'))
    if (b) { b.click(); return true }
    return false
  })()`)
  check('找到并点击「生成并分发」', opened === true)
  check('对话框已打开',
    await waitFor(`[...document.querySelectorAll('.el-dialog')].some(d => d.innerText.includes('生成并分发'))`, 10000))

  // ---- 交互辅助（第 3、4 步共用）-----------------------------------------
  // 必须用 **CDP 真实鼠标事件**：合成 DOM 事件对 Element Plus 的下拉不生效 ——
  // 之前事件发出去了、脚本还报 PASS，但模型根本没变，提交时页面如实报
  // "请先选择发送方与接收方节点"。
  // 另一个坑：**每次选完都要按 Esc 收起浮层**。否则浮层盖在对话框上，
  // 后续点击落在浮层里，下一个下拉根本打不开（现象是"选项不可见"）。
  const mouseClick = async (x, y) => {
    await rpc('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1, buttons: 1 })
    await rpc('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1, buttons: 1 })
  }
  const pressEscape = async () => {
    await rpc('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
    await rpc('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
    await sleep(400)
  }
  const rectOf = (expr) => ev(`(() => {
    const el = ${expr}
    if (!el) return null
    const r = el.getBoundingClientRect()
    if (r.width <= 0 || r.height <= 0) return null
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
  })()`)
  const dialogSelect = (i) => `[...[...document.querySelectorAll('.el-dialog')].find(d => d.innerText.includes('生成并分发')).querySelectorAll('.el-select')][${i}]`
  const inputRectOf = (i) => rectOf(`${dialogSelect(i)}.querySelector('input')`)
  const clickInput = async (i) => {
    const rect = await inputRectOf(i)
    if (!rect) return false
    await mouseClick(rect.x, rect.y)
    return await waitFor(`[...document.querySelectorAll('.el-select-dropdown__item')].some(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 })`, 6000)
  }
  const visibleOptions = () => ev(`[...document.querySelectorAll('.el-select-dropdown__item')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 })
    .map(e => e.innerText.trim())`)
  const optionRectOf = (keyword) => rectOf(`[...document.querySelectorAll('.el-select-dropdown__item')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 })
    .find(e => e.innerText.includes(${JSON.stringify(keyword)}))`)

  // 打开下拉并**当场**选中：不"先开一次读、再开一次选" ——
  // 实测同一个 select 在按过 Esc 之后再点，浮层不再弹出（选项永远"不可见"）。
  // 所以：一次打开 → 读选项 → 直接点中目标项 → Esc 收起。
  const openAndPick = async (index, keyword) => {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (!(await clickInput(index))) return { ok: false, options: [], shown: '(下拉未找到)' }
      const options = (await visibleOptions()) || []
      if (!options.length) { await pressEscape(); continue }
      const rect = await optionRectOf(keyword)
      if (!rect) { await pressEscape(); return { ok: false, options, shown: '(目标选项不存在)' } }
      await mouseClick(rect.x, rect.y)
      await sleep(800)
      await pressEscape()
      // 读"选中了什么"要看 select 的**可见文本**：Element Plus 的 el-select
      // 在非过滤态下 input.value 就是空字符串，选中项渲染在旁边那个 span 里。
      // 之前读 input.value，于是选中明明成功了却全报 FAIL。
      const shown = await ev(`${dialogSelect(index)}.innerText.replace(/\\s+/g, ' ').trim()`)
      if (String(shown).includes(keyword)) return { ok: true, options, shown }
      return { ok: false, options, shown }
    }
    return { ok: false, options: [], shown: '(下拉未能打开)' }
  }

  console.log('\n=== 3. 「封装算法」选择器：一次打开、读选项并选中 Falcon ===')
  const algoPick = await openAndPick(0, 'Falcon')
  check('算法下拉可打开并读到选项', (algoPick.options || []).length > 0, JSON.stringify(algoPick.options || []))
  check('算法选项包含 Kyber KEM', (algoPick.options || []).some((o) => /Kyber/.test(o)))
  check('算法选项包含 Falcon 格密码', (algoPick.options || []).some((o) => /Falcon/.test(o)))
  check('已选中 Falcon 格密码', algoPick.ok, `下拉显示="${algoPick.shown}"`)

  console.log('\n=== 4. 选两个节点并提交 ===')
  // 基线（batchesBefore）已在第 1 步表格渲染后取好，这里不再重复取 ——
  // 之前在这里重取，用的是对话框打开后的旧页面数据，和第 5 步读到的不是同一份，会假通过。

  const senderPick = await openAndPick(1, SENDER)
  check(`选中发送方 ${SENDER}`, senderPick.ok, `下拉显示="${senderPick.shown}"`)
  const receiverPick = await openAndPick(2, RECEIVER)
  check(`选中接收方 ${RECEIVER}`, receiverPick.ok, `下拉显示="${receiverPick.shown}"`)

  const submitted = await ev(`(() => {
    const dialog = [...document.querySelectorAll('.el-dialog')].find(d => d.innerText.includes('生成并分发'))
    const b = [...dialog.querySelectorAll('button')].find(x => x.innerText.trim() === '生成并分发')
    if (b) { b.click(); return true }
    return false
  })()`)
  check('点击「生成并分发」提交', submitted === true)
  await sleep(12000)

  const dialogState = await ev(`(() => {
    const dialog = [...document.querySelectorAll('.el-dialog')].find(d => d.innerText.includes('生成并分发'))
    if (!dialog) return { gone: true }
    return { result: dialog.querySelector('.dialog-ok')?.innerText.trim() || '',
             error: dialog.querySelector('.dialog-error')?.innerText.trim() || '' }
  })()`)
  console.log(`  对话框结果: ${JSON.stringify(dialogState)}`)
  check('提交后无报错', !dialogState.error, dialogState.error || '')
  check('返回了 Falcon 池生成结果', /Falcon/.test(dialogState.result || ''), dialogState.result || '')
  // 本次生成的批次号直接从**提交结果**里取 —— 不依赖列表渲染，
  // 这样后面的数据库校验就不会被界面抖动带偏。
  const newBatch = (dialogState.result || '').match(/pool_falcon_[0-9a-f]+/)?.[0] || ''
  check('从提交结果里取到新批次号', Boolean(newBatch), newBatch || '(未取到)')

  console.log('\n=== 5. 列表里出现 Falcon 行 ===')
  // 重新加载页面再读（点页面上的"刷新"按钮不可靠），并允许重载一次：
  // SPA 首次加载偶尔落在初始化过程中，表格迟迟不渲染。
  const readRows = () => ev(`(() => {
    const root = [...document.querySelectorAll('.el-table')].find(t => t.querySelector('.el-table__header'))
    const headers = [...(root?.querySelectorAll('.el-table__header th') || [])].map(th => th.innerText.trim())
    const algoIdx = headers.indexOf('算法')
    const batchIdx = headers.indexOf('批次号')
    const ownerIdx = headers.findIndex(h => h.includes('归属'))
    return [...(root?.querySelectorAll('.el-table__body tbody tr') || [])].map(tr => {
      const tds = [...tr.querySelectorAll('td')]
      return {
        batch: tds[batchIdx]?.innerText.trim(),
        algo: tds[algoIdx]?.innerText.trim(),
        owner: ownerIdx >= 0 ? tds[ownerIdx]?.innerText.trim() : ''
      }
    })
  })()`)
  let rows = []
  for (let attempt = 0; attempt < 3 && rows.length === 0; attempt++) {
    await rpc('Page.navigate', { url: `${ORIGIN}${PAGE}` })
    await waitFor(`document.querySelectorAll('.el-table__body tbody tr').length > 0`, 20000)
    rows = (await readRows()) || []
  }
  const falconRows = (rows || []).filter((r) => /Falcon/i.test(r.algo || ''))
  // 断言以**提交结果里的批次号**为准（不靠"列表里没出现过"来推断）
  const newFalconRows = falconRows.filter((r) => r.batch === newBatch)
  console.log(`  当前池内行（前 4）: ${JSON.stringify((rows || []).slice(0, 4))}`)
  check('密钥池列表出现 Falcon 格密码行', falconRows.length > 0, JSON.stringify(falconRows.slice(0, 2)))
  check('列表里能定位到本次提交生成的 Falcon 批次',
    newFalconRows.length > 0, `期望批次=${newBatch}，列表批次去重=${JSON.stringify([...new Set(falconRows.map((r) => r.batch))].slice(0, 3))}`)
  // 「归属节点」是**池子的持有者**（发送方），而 Falcon 封装用的是**接收方**公钥 ——
  // 两个不同字段，别混。界面只显示归属方，所以这里断言归属方=发送方，
  // 接收方另用数据库求证（下一条）。
  check('新增 Falcon 批次归属所选的发送方（池子持有者）',
    newFalconRows.some((r) => /演示节点1|DEMO-NODE-01/.test(r.owner || '')),
    `归属节点=${JSON.stringify([...new Set(newFalconRows.map((r) => r.owner))])}`)

  // 数据库求证：node1=发送方、node2=接收方（用提交结果里的批次号，不依赖列表）
  if (newBatch) {
    const pair = execSync(
      `docker exec kms_mysql mysql -uroot -proot123456 -N -e "` +
      `select concat(b.node_id,'->',c.node_id) from falcon_kds.dvadmin_pqkds_pre_distributed_keys k ` +
      `join falcon_kds.dvadmin_pqkds_nodes b on b.id=k.node1_id ` +
      `join falcon_kds.dvadmin_pqkds_nodes c on c.id=k.node2_id ` +
      `where k.pool_id='${newBatch}' limit 1;" 2>nul`,
      { encoding: 'utf8' }
    ).trim()
    check('数据库里该批次的 node1→node2 与所选一致（发送方→接收方）',
      pair === `${SENDER}->${RECEIVER}`, `实际=${pair}`)
  } else {
    check('数据库里该批次的 node1→node2 与所选一致（发送方→接收方）', false, '未取到新批次号')
  }

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
