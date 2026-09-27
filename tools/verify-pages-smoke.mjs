// 逐页冒烟测试：把管理端与用户前台的每个页面都打开一遍，确认
//   1) 主区域渲染出内容（不是空白）
//   2) 没有 Vue 渲染报错 / 接口超时提示
//   3) 控制台没有 error 级日志
// 用途：文案清理动了模板标记，必须确认没有把哪个页面改坏。
//
// 用法：node tools/verify-pages-smoke.mjs
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const CDP_PORT = 9236
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))

// 管理端：菜单表里 menu_type='C' 的路径（parent.path/child.path）
const ADMIN_PAGES = [
  ['/updatedel/index', '总览仪表盘'],
  ['/updatedel/distchain/overview', '分发总览'],
  ['/updatedel/distchain/keypool', '密钥池'],
  ['/updatedel/distchain/sessions', '会话密钥'],
  ['/updatedel/distchain/distlogs', '分发日志'],
  ['/updatedel/distchain/chain', '区块链存证'],
  ['/updatedel/distchain/nodes', '节点管理'],
  ['/updatedel/nodeauth/index', '节点分发授权'],
  ['/updatedel/key/keyupdate', '密钥更新'],
  ['/updatedel/key/history', '生成历史'],
  ['/updatedel/key/common-param', '公共参数'],
  ['/updatedel/key/keyautoupdate', '密钥自动更新'],
  ['/updatedel/key/keydelete', '密钥回收'],
  ['/updatedel/query/key-list', '密钥查询'],
  ['/updatedel/query/public-keys', '公共密钥'],
  ['/updatedel/query/user-keys', '用户密钥池'],
  ['/updatedel/algorithm/demo', '算法说明'],
  ['/updatedel/algorithm/quick', '算法速览'],
  ['/updatedel/algorithm/process', '算法流程'],
  ['/updatedel/audit/permission/request', '权限审批'],
  ['/updatedel/system/user', '用户管理'],
  ['/updatedel/system/role', '角色管理'],
  ['/updatedel/system/menu', '菜单管理'],
  ['/updatedel/audit/log/operlog', '操作日志'],
  ['/updatedel/testing/acceptance', '验收测试']
]
const USER_PAGES = [
  ['/user/workbench', '工作台'],
  ['/user/generate/index', '密钥生成'],
  ['/user/lifecycle/index', '更新与回收'],
  ['/user/distribute/index', '密钥分发'],
  ['/user/symmetric-keys/index', '对称密钥查看'],
  ['/user/my-logs/index', '我的操作日志']
]

const results = []
function check(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`  ${pass ? '[PASS]' : '[FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const dir = mkdtempSync(join(tmpdir(), 'smoke-'))
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
const waitFor = async (expr, timeoutMs = 15000) => {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try { if (await ev(expr)) return true } catch {}
    await sleep(350)
  }
  return false
}

let consoleErrors = []
try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
    if (!t) await sleep(500)
  }
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params?.type)) {
      const text = (m.params.args || []).map((a) => a.value || a.description || '').join(' ').slice(0, 200)
      if (/Vue warn|TypeError|ReferenceError|is not a function|Cannot read/.test(text)) consoleErrors.push(text)
    }
    if (m.method === 'Runtime.exceptionThrown') {
      consoleErrors.push(String(m.params?.exceptionDetails?.text || '').slice(0, 200))
    }
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')

  console.log('\n=== 管理端逐页 ===')
  const adminToken = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` }); await sleep(2500)
  await ev(`document.cookie = 'Admin-Token=${adminToken}; path=/'`)
  for (const [path, name] of ADMIN_PAGES) {
    consoleErrors = []
    await rpc('Page.navigate', { url: `${ORIGIN}${path}` })
    await waitFor(`document.querySelector('.app-main') && document.querySelector('.app-main').innerText.trim().length > 30`, 12000)
    const state = await ev(`(() => {
      const main = document.querySelector('.app-main')
      const text = (main?.innerText || '').replace(/\\s+/g, ' ')
      return {
        len: text.length,
        sample: text.slice(0, 90),
        timeout: text.includes('系统接口请求超时'),
        iframe: Boolean(document.querySelector('.app-main iframe'))
      }
    })()`)
    check(`${name}  (${path})`,
      // iframe 页（如「验收测试」）本身没有文本，只要 iframe 在就算正常；
      // 内容很短的页面（表格为空）也正常 —— 关键是别空白、别报错、别超时。
      !state.timeout && consoleErrors.length === 0 && (state.iframe || state.len > 25),
      state.timeout ? '接口超时' : (consoleErrors[0] || (state.iframe ? 'iframe 页' : state.sample)))
  }

  console.log('\n=== 用户前台逐页 ===')
  const userToken = await login(ORIGIN, '/lifecycle-api', 'yx', 'admin123')
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` }); await sleep(2000)
  await ev(`document.cookie = 'Admin-Token=${userToken}; path=/'`)
  for (const [path, name] of USER_PAGES) {
    consoleErrors = []
    await rpc('Page.navigate', { url: `${ORIGIN}${path}` })
    await waitFor(`document.body.innerText.trim().length > 100`, 12000)
    const state = await ev(`(() => {
      const text = (document.body.innerText || '').replace(/\\s+/g, ' ')
      return { len: text.length, sample: text.slice(0, 90), timeout: text.includes('系统接口请求超时') }
    })()`)
    check(`${name}  (${path})`,
      state.len > 100 && !state.timeout && consoleErrors.length === 0,
      state.timeout ? '接口超时' : (consoleErrors[0] || state.sample))
  }

  const pass = results.filter((r) => r.pass).length
  console.log(`\n=== 结果：${pass}/${results.length} 页正常 ===`)
  if (pass !== results.length) {
    console.log('异常页面：')
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