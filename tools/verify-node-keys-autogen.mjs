// =============================================================================
// verify-node-keys-autogen.mjs —— 验证「新建节点自动生成三套密钥」闭环
// -----------------------------------------------------------------------------
// 背景（2026-09-26）：
//   1) 新建节点此前只自动生成 **Kyber**，Falcon 必须在界面上手动补、国密不生成；
//   2) 列表接口把 falcon_public_key（约 7.8MB/节点）一起返回，3 个节点就 23.4MB；
//   3) 「国密密钥」列因为后端不返回 gm_public_key，**永远显示"未生成"**，
//      连带"重新生成"按钮文案不变、覆盖告警也不弹。
//
// 本次改造后应当满足：
//   * 新建一个演示节点，三列（Kyber / Falcon / 国密）**都**变成"已就绪"；
//   * 列表接口不返回公钥本身，只回 *_key_ready 布尔值（体积应在 KB 级）；
//   * 「密钥」弹窗显示公钥指纹、国密公钥与安全级别。
//
// 用法：node tools/verify-node-keys-autogen.mjs
// =============================================================================
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const CDP_PORT = 9236
const PAGE = '/updatedel/distchain/nodes'
const TEST_NODE_ID = process.argv[2] || `VERIFY-AUTOGEN-${Date.now().toString().slice(-6)}`
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

const dir = mkdtempSync(join(tmpdir(), 'nodeautogen-'))
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
const waitFor = async (expr, timeoutMs = 20000, intervalMs = 500) => {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try { if (await ev(expr)) return true } catch {}
    await sleep(intervalMs)
  }
  return false
}
const clickByText = (selector, text) => ev(`(() => {
  const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.innerText.trim().includes(${JSON.stringify(text)}))
  if (el) { el.click(); return true }
  return false
})()`)

/** 读某一行的三列密钥状态（按表头位置取，避免列顺序变化导致错位） */
const rowState = (nodeId) => ev(`(() => {
  const tr = [...document.querySelectorAll('.el-table__body tbody tr')].find(t => t.innerText.includes(${JSON.stringify(nodeId)}))
  if (!tr) return null
  const headers = [...document.querySelectorAll('.el-table__header th')].map(th => th.innerText.trim())
  const tds = [...tr.querySelectorAll('td')]
  const at = (h) => tds[headers.indexOf(h)]?.innerText.trim()
  return { kyber: at('Kyber 密钥'), falcon: at('Falcon 密钥'), gm: at('国密密钥') }
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

  console.log('\n=== 1. 管理员登录并进入节点管理 ===')
  const token = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
  check('管理员登录成功', Boolean(token))
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` }); await sleep(2500)
  await ev(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${PAGE}` })
  check('节点管理页已渲染', await waitFor(`document.querySelectorAll('.el-table__body tbody tr').length > 0`, 25000))

  console.log('\n=== 2. 列表接口已瘦身（不返回公钥本身）===')
  const listStats = await ev(`(async () => {
    const res = await fetch('/pqkds-api/nodes/?page=1&limit=500', { headers: { Authorization: 'Bearer ${token}' } })
    const text = await res.text()
    const body = JSON.parse(text)
    const row = (body.data || [])[0] || {}
    return {
      bytes: text.length,
      count: (body.data || []).length,
      hasFalconKey: 'falcon_public_key' in row,
      hasKyberKey: 'kyber_public_key' in row,
      hasReadyFlags: ['kyber_key_ready','falcon_key_ready','gm_key_ready','sscl_key_ready'].every(k => k in row)
    }
  })()`)
  console.log(`  列表接口: ${listStats?.bytes} 字节 / ${listStats?.count} 个节点`)
  check('列表不返回 falcon_public_key', listStats?.hasFalconKey === false)
  check('列表不返回 kyber_public_key', listStats?.hasKyberKey === false)
  check('列表返回四个 *_key_ready 布尔值', listStats?.hasReadyFlags === true)
  // 改造前实测 3 个节点 23.4MB；现在应当只有 KB 级
  check('列表体积在 KB 级（<64KB）', (listStats?.bytes || 0) < 65536, `${listStats?.bytes} 字节`)

  console.log(`\n=== 3. 新建演示节点，三套密钥应自动生成 ${TEST_NODE_ID} ===`)
  check('点击「新增演示节点」', (await clickByText('button', '新增演示节点')) === true)
  check('新建对话框已打开', await waitFor(`[...document.querySelectorAll('.el-dialog')].some(d => d.innerText.includes('节点ID'))`, 10000))
  const dlgText = await ev(`(() => {
    const d = [...document.querySelectorAll('.el-dialog')].find(x => x.innerText.includes('节点ID'))
    return d ? d.innerText.replace(/\\s+/g, ' ') : ''
  })()`)
  check('对话框说明了三套密钥与耗时', /Kyber/.test(dlgText) && /国密/.test(dlgText) && /Falcon/.test(dlgText) && /20 ?秒|十几秒/.test(dlgText),
    (dlgText || '').slice(-90))

  const filled = await ev(`(() => {
    const dialog = [...document.querySelectorAll('.el-dialog')].find(d => d.innerText.includes('节点ID'))
    const setVal = (el, v) => {
      const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      s.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
      el.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const byLabel = (label) => {
      const item = [...dialog.querySelectorAll('.el-form-item')].find(i => i.querySelector('.el-form-item__label')?.innerText.trim() === label)
      return item?.querySelector('input')
    }
    const idEl = byLabel('节点ID'), nameEl = byLabel('节点名称'), ipEl = byLabel('IP 地址')
    if (!idEl || !nameEl || !ipEl) return false
    setVal(idEl, ${JSON.stringify(TEST_NODE_ID)})
    setVal(nameEl, '自动生成验证节点')
    setVal(ipEl, '127.0.0.98')
    return true
  })()`)
  check('填写节点信息', filled === true)

  const t0 = Date.now()
  check('提交创建', (await clickByText('.el-dialog button', '确 定')) === true || (await clickByText('.el-dialog button', '确定')) === true)
  // 注册会同步跑 Kyber + 国密 + Falcon（KGC 部分私钥 + 密钥对），实测约 18 秒
  const created = await waitFor(`[...document.querySelectorAll('.el-table__body tbody tr')].some(tr => tr.innerText.includes(${JSON.stringify(TEST_NODE_ID)}))`, 120000)
  const elapsed = Math.round((Date.now() - t0) / 1000)
  check('新节点已出现在列表', created, `耗时约 ${elapsed}s`)
  check('创建耗时在合理区间（10~60s）', elapsed >= 10 && elapsed <= 60, `${elapsed}s`)

  console.log('\n=== 4. 三列密钥状态（关键断言）===')
  const st = await rowState(TEST_NODE_ID)
  console.log(`  该行状态: ${JSON.stringify(st)}`)
  check('Kyber 列已就绪', /已就绪|已上传/.test(st?.kyber || ''), st?.kyber)
  check('Falcon 列已就绪（自动生成）', /已就绪|已生成/.test(st?.falcon || ''), st?.falcon)
  check('国密列已就绪（此前恒为"未生成"）', /已就绪/.test(st?.gm || ''), st?.gm)

  console.log('\n=== 5. 「密钥」弹窗内容 ===')
  check('打开该节点的「密钥」', (await ev(`(() => {
    const tr = [...document.querySelectorAll('.el-table__body tbody tr')].find(t => t.innerText.includes(${JSON.stringify(TEST_NODE_ID)}))
    const btn = tr && [...tr.querySelectorAll('button')].find(b => b.innerText.trim() === '密钥')
    if (btn) { btn.click(); return true }
    return false
  })()`)) === true)
  check('密钥对话框已打开', await waitFor(`[...document.querySelectorAll('.el-dialog')].some(d => d.innerText.includes('节点密钥'))`, 10000))
  // ⚠️ 弹窗打开后 keys 接口**还没回来**，此时读文本会拿到"（未生成）"占位。
  // 必须轮询等到接口数据渲染完成，否则断言的是加载态而不是结果（踩过）。
  const keysLoaded = await waitFor(`(() => {
    const d = [...document.querySelectorAll('.el-dialog')].find(x => x.innerText.includes('节点密钥'))
    if (!d) return false
    const t = d.innerText.replace(/\\s+/g, ' ')
    return /国密公钥（SM2）\\s*04[0-9a-f]{20}/.test(t) && /Kyber 安全级别\\s*5\\d\\d/.test(t)
  })()`, 20000)
  check('密钥数据已渲染完成', keysLoaded)
  const keysText = await ev(`(() => {
    const d = [...document.querySelectorAll('.el-dialog')].find(x => x.innerText.includes('节点密钥'))
    return d ? d.innerText.replace(/\\s+/g, ' ') : ''
  })()`)
  check('显示 Kyber 安全级别', /Kyber 安全级别\s*5\d\d/.test(keysText || ''))
  check('显示 Falcon 安全级别', /Falcon 安全级别\s*5\d\d/.test(keysText || ''))
  check('国密公钥已不再显示"未生成"', /国密公钥（SM2）\s*04[0-9a-f]{20}/.test(keysText || ''))
  check('SSCL 公钥已不再显示"未生成"', /国密公钥（SSCL）\s*04[0-9a-f]{20}/.test(keysText || ''))
  check('说明里点明指纹而非全量公钥', /指纹/.test(keysText || ''))
  // 按钮文案应变成"重新生成"，这正是之前恒为"生成"的那个 bug
  check('国密按钮文案变为「重新生成」', /重新生成国密密钥/.test(keysText || ''))
  check('Falcon 按钮文案变为「重新生成」', /重新生成 Falcon 密钥/.test(keysText || ''))
  // 指纹必须是可区分的哈希，不能是每个节点都一样的 "COMPRESSED:eNp…" 压缩头
  check('公钥指纹不是无区分度的压缩头', !/COMPRESSED:eNp/.test(keysText || ''))

  console.log('\n=== 6. 清理测试节点 ===')
  await ev(`(() => {
    const close = [...document.querySelectorAll('.el-dialog__headerbtn')]
    if (close.length) close[close.length - 1].click()
  })()`)
  await sleep(600)
  const cleaned = await ev(`(() => {
    const tr = [...document.querySelectorAll('.el-table__body tbody tr')].find(t => t.innerText.includes(${JSON.stringify(TEST_NODE_ID)}))
    const btn = tr && [...tr.querySelectorAll('button')].find(b => b.innerText.trim() === '删除')
    if (btn) { btn.click(); return true }
    return false
  })()`)
  await sleep(1200)
  const confirmDel = await ev(`(() => {
    const box = [...document.querySelectorAll('.el-message-box')].find(b => b.innerText.includes('确定删除'))
    const btn = box && [...box.querySelectorAll('button')].find(b => /确定|删 除/.test(b.innerText))
    if (btn) { btn.click(); return true }
    return false
  })()`)
  const gone = await waitFor(`![...document.querySelectorAll('.el-table__body tbody tr')].some(tr => tr.innerText.includes(${JSON.stringify(TEST_NODE_ID)}))`, 25000)
  check('测试节点已删除（保持演示数据干净）', cleaned && confirmDel && gone)

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
