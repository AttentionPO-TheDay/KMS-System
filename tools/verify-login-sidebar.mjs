// =============================================================================
// verify-login-sidebar.mjs —— 验证「普通用户登录后侧边栏立即出现」
// -----------------------------------------------------------------------------
// 修的 bug（2026-09-26）：普通用户登录后侧边栏空白，必须刷新一下才出来。
//
// 成因（走代码就能看出来）：
//   * 登录页 login.vue 在跳转前先 `await userStore.getInfo()` —— roles 被写入；
//   * 随后 `router.push(...)` 是 **SPA 内跳转**，路由守卫随即执行；
//   * 而守卫写的是 `if (roles.length === 0) { getInfo → generateRoutes }`，
//     角色已有 → 直接 `next()`，**动态路由从未生成** → 侧边栏没数据；
//   * 刷新时 roles 从空开始，守卫走完整流程，菜单就出来了。
//   管理员碰不到：他们登录后是 `window.location.replace()` 整页跳转，等于重新加载。
//
// 本脚本用真实浏览器走完整登录流程（含图形验证码：从页面自己的 /captchaImage
// 响应里取 uuid，再去 Redis 读答案 —— 不能用自己另取的那张，uuid 对不上），
// 然后断言 **不刷新** 的情况下侧边栏已经有菜单项。
//
// 用法：node tools/verify-login-sidebar.mjs [username] [password]
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const USERNAME = process.argv[2] || 'yx'
const PASSWORD = process.argv[3] || 'admin123'
const ORIGIN = 'http://127.0.0.1'
const CDP_PORT = 9230
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

// 从 Redis 取某张验证码的答案（页面自己取的那张，uuid 必须匹配）
function captchaAnswer(uuid) {
  const raw = execFileSync('docker',
    ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`],
    { encoding: 'utf8' }).trim()
  if (!raw) return ''
  // Spring 的 RedisTemplate 用 JSON 序列化，字符串带引号，必须剥掉
  return raw.replace(/^"(.*)"$/s, '$1')
}

const dir = mkdtempSync(join(tmpdir(), 'sidebar-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const handlers = []
const rpc = (method, params = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.id === n) { ws.removeEventListener('message', on); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method, params }))
})
const ev = async (expr) => (await rpc('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.value

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
    if (m.method) handlers.forEach((h) => h(m))
  })
  await rpc('Runtime.enable')
  await rpc('Page.enable')
  await rpc('Network.enable')

  // 抓页面自己那次 /captchaImage 的响应，拿它的 uuid
  let pageCaptchaUuid = ''
  handlers.push((m) => {
    if (m.method === 'Network.responseReceived' && /captchaImage/.test(m.params?.response?.url || '')) {
      rpc('Network.getResponseBody', { requestId: m.params.requestId })
        .then((r) => {
          try { pageCaptchaUuid = JSON.parse(r.body).uuid || '' } catch {}
        }).catch(() => {})
    }
  })

  console.log('\n=== 1. 打开登录页，取页面自己的验证码 uuid ===')
  await rpc('Page.navigate', { url: `${ORIGIN}/user/login` })
  await sleep(5000)
  check('页面已加载登录表单', Boolean(await ev(`!!document.querySelector('input[placeholder="账号"]')`)))
  check('捕获到页面自身的验证码 uuid', Boolean(pageCaptchaUuid), pageCaptchaUuid || '未捕获')

  const answer = captchaAnswer(pageCaptchaUuid)
  check('从 Redis 取到该 uuid 的答案', Boolean(answer), `答案=${answer}`)

  console.log('\n=== 2. 填表并登录（SPA 内跳转，不刷新）===')
  await ev(`(() => {
    const setVal = (el, v) => {
      const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      s.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
      el.dispatchEvent(new Event('change', { bubbles: true }))
    }
    setVal(document.querySelector('input[placeholder="账号"]'), ${JSON.stringify(USERNAME)})
    setVal(document.querySelector('input[placeholder="密码"]'), ${JSON.stringify(PASSWORD)})
    setVal(document.querySelector('input[placeholder="验证码"]'), ${JSON.stringify(answer)})
    return true
  })()`)
  await sleep(600)
  await ev(`(() => {
    const btn = [...document.querySelectorAll('button')].find(b => /登\\s*录/.test(b.innerText))
    if (btn) { btn.click(); return true }
    return false
  })()`)
  await sleep(9000)

  console.log('\n=== 3. 登录后（未刷新）侧边栏是否已有菜单 ===')
  const state = await ev(`(() => {
    const items = [...document.querySelectorAll('.sidebar-container .el-menu-item, .sidebar-container .el-sub-menu__title')]
      .map(el => el.innerText.trim()).filter(Boolean)
    return {
      url: location.href,
      itemCount: items.length,
      items: items.slice(0, 12),
      hasSidebar: Boolean(document.querySelector('.sidebar-container')),
      isEmptyText: (document.querySelector('.sidebar-container')?.innerText || '').trim().length === 0
    }
  })()`)
  console.log(`  当前地址: ${state.url}`)
  console.log(`  菜单项: ${JSON.stringify(state.items)}`)
  check('登录后已在站内（不是停在登录页）', !/\/login/.test(state.url), state.url)
  check('侧边栏存在', state.hasSidebar === true)
  check('侧边栏已渲染菜单项（无需刷新）', state.itemCount > 0, `${state.itemCount} 项`)

  const pass = results.filter((r) => r.pass).length
  console.log(`\n=== 结果：${pass}/${results.length} 通过 ===`)
  if (pass !== results.length) {
    process.exitCode = 1
  }
} catch (error) {
  console.error('\n执行失败:', error.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch {}
  chrome.kill()
}
