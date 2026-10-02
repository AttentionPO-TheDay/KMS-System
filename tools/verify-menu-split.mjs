// =============================================================================
// verify-menu-split.mjs —— 验证管理端 / 节点端是**两棵独立的侧边栏树**
// -----------------------------------------------------------------------------
// 判据是**渲染后的 DOM**，不是数据库。
// 数据库里排好了不等于界面对：菜单走 sys_menu → /getRouters → vue-router
// 动态注册 → Sidebar 渲染，中间任何一环出问题都表现为"库里对、界面不对"。
// 这正是本次要修的问题（用户反馈"进去后就是一个公共的侧边栏"）。
//
// 断言两件事：
//   1. 管理端与节点端渲染出来的菜单**不同**，且各自包含/不包含该有的项
//   2. 每个叶子菜单**点得开** —— 不落到 /401 或 SPA 的 404 兜底路由
//
// 用法：
//   node tools/verify-menu-split.mjs
//   node tools/verify-menu-split.mjs --origin http://127.0.0.1 --base /updatedel
//
// 需要：容器已起（kms_gateway / kms_mysql / kms_redis），本机有 Chrome 或 Edge。
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const argv = process.argv.slice(2)
const option = (name, fallback = '') => {
  const inline = argv.find((v) => v.startsWith(`--${name}=`))
  if (inline) return inline.slice(name.length + 3)
  const i = argv.indexOf(`--${name}`)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}

const ORIGIN = option('origin', 'http://127.0.0.1').replace(/\/$/, '')
const BASE = option('base', '/updatedel')
/** 登录/验证码走 RuoYi 的 API 前缀（见 front/.env.production 的 VITE_APP_BASE_API） */
const API = option('api', '/lifecycle-api')
const CDP_PORT = Number(option('cdp-port', '9277'))
const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find((p) => existsSync(p))

// 两棵树各自**必须**出现 / **必须**不出现的菜单名。
// 只列有区分度的项：两边同名的（如「工作台」只在节点端）不必列全，
// 关键是能证明"两棵树不一样，且各归各位"。
const ADMIN_MUST = ['密钥生成监管', '密钥更新与回收监管', '密钥分发监管', '节点管理', '区块链存证', '验收测试台', '域管理', '异常密钥', '跨域分发']
const ADMIN_MUST_NOT = ['工作台', '发起分发', '我的密钥', '本地密钥环境', '预分配', '密钥池']
const NODE_MUST = ['工作台', '密钥生成', '更新与回收', '密钥分发', '节点信息', '当前节点', '本地密钥环境', '我的日志', '预分配', '密钥池', '会话管理', '发起分发']
const NODE_MUST_NOT = ['密钥生成监管', '密钥更新与回收监管', '密钥分发监管', '节点管理', '节点授权', '域管理', '异常密钥', '跨域分发', '区块链存证', '验收测试台', '操作日志']

const results = []
const check = (name, pass, detail = '') => {
  results.push({ name, pass, detail })
  console.log(`  ${pass ? '[PASS]' : '[FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 节点端账号。默认取 role_id=2 且已映射到节点的账号。 */
const NODE_USER = option('node-user') || process.env.MENU_NODE_USER || ''
const NODE_PASS = option('node-pass') || process.env.MENU_NODE_PASS || ''
/** 节点账号的密码来自建节点流程；未提供时该部分跳过而不是猜 */
const ADMIN_USER = option('admin-user', 'admin')
const ADMIN_PASS = option('admin-pass', 'admin123')

function captchaAnswer(uuid) {
  const raw = execFileSync('docker',
    ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`],
    { encoding: 'utf8' }).trim()
  if (!raw) return ''
  return raw.replace(/^"(.*)"$/s, '$1')
}

const dir = mkdtempSync(join(tmpdir(), 'menusplit-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const rpc = (method, params = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.id === n) {
      ws.removeEventListener('message', on)
      m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result)
    }
  }
  ws.addEventListener('message', on)
  ws.send(JSON.stringify({ id: n, method, params }))
})
const ev = async (expr) => {
  const r = await rpc('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })
  return r.result?.value
}

try {
  let target = null
  for (let i = 0; i < 40 && !target; i++) {
    try {
      target = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((t) => t.type === 'page')
    } catch { /* 浏览器还没起来 */ }
    if (!target) await sleep(500)
  }
  if (!target) throw new Error('拿不到 CDP page target')

  ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable')
  await rpc('Page.enable')

  /** 用真实登录页登录（验证码从 Redis 取），然后 dump 侧边栏。 */
  async function loginAndDump(user, pass, label) {
    await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
    await sleep(3500)

    const loginRes = await ev(`(async () => {
      const capRes = await fetch('${API}/captchaImage')
      const cap = await capRes.json()
      return { uuid: cap.uuid, hasImg: !!cap.img }
    })()`)
    if (!loginRes?.uuid) throw new Error(`${label}: 取不到验证码 uuid`)

    const answer = captchaAnswer(loginRes.uuid)
    if (!answer) throw new Error(`${label}: Redis 里没有验证码答案（容器没起？）`)

    const out = await ev(`(async () => {
      const res = await fetch('${API}/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: ${JSON.stringify(user)}, password: ${JSON.stringify(pass)},
                               code: ${JSON.stringify(answer)}, uuid: ${JSON.stringify(loginRes.uuid)} })
      })
      const j = await res.json()
      if (!j.token) return { ok: false, code: j.code, msg: j.msg }
      document.cookie = 'Admin-Token=' + j.token + '; path=/'
      return { ok: true }
    })()`)
    if (!out?.ok) throw new Error(`${label}: 登录失败 ${out?.msg || out?.code}`)

    // 整页重载，让守卫走完整流程（动态路由才会注册）
    await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/index` })
    await sleep(4000)

    return await ev(`(() => {
      const items = [...document.querySelectorAll('.sidebar-container .el-menu-item, .sidebar-container .el-sub-menu__title')]
      return {
        url: location.pathname + location.hash,
        menus: items.map(el => (el.querySelector('.menu-title') || el).innerText.trim()).filter(Boolean),
        hrefs: [...document.querySelectorAll('.sidebar-container a')].map(a => a.getAttribute('href')).filter(Boolean)
      }
    })()`)
  }

  // ---- 管理员 ----
  console.log('\n== 管理端（admin）==')
  const admin = await loginAndDump(ADMIN_USER, ADMIN_PASS, 'admin')
  check('管理端侧边栏有菜单', admin.menus.length > 0, `${admin.menus.length} 项`)
  for (const m of ADMIN_MUST) {
    check(`管理端含「${m}」`, admin.menus.includes(m))
  }
  for (const m of ADMIN_MUST_NOT) {
    check(`管理端不含「${m}」`, !admin.menus.includes(m))
  }

  // ---- 页面可达性：**在 admin 会话里**逐个点开（换会话后动态路由不同，会误判 404）----
  console.log('\n== 页面可达性（管理端逐页点开）==')
  let bad = 0
  for (const href of [...new Set(admin.hrefs)]) {
    await rpc('Page.navigate', { url: `${ORIGIN}${BASE}${href.startsWith('/') ? href : '/' + href}` })
    await sleep(1800)
    const st = await ev(`({ url: location.href, len: document.body.innerText.trim().length })`)
    const fell404 = st.url.includes('404') || st.len < 40
    const fell401 = st.url.includes('401')
    if (fell401 || fell404) {
      bad++
      check(`可打开 ${href}`, false, `落到 ${st.url.includes('401') ? '401' : '404/空白'}`)
    } else {
      check(`可打开 ${href}`, true)
    }
  }
  check('管理端无死链', bad === 0, bad ? `${bad} 个页面打不开` : '')

  // ---- 节点端（放在可达性之后：换会话会重置动态路由）----
  if (!NODE_USER || !NODE_PASS) {
    console.log('\n== 节点端：跳过 ==')
    check('节点端验证', false,
      '未提供节点账号。用 --node-user/--node-pass 或 MENU_NODE_USER/MENU_NODE_PASS 指定一个已映射到节点的账号')
  } else {
    console.log(`\n== 节点端（${NODE_USER}）==`)
    const node = await loginAndDump(NODE_USER, NODE_PASS, 'node')
    check('节点端侧边栏有菜单', node.menus.length > 0, `${node.menus.length} 项`)
    for (const m of NODE_MUST) {
      check(`节点端含「${m}」`, node.menus.includes(m))
    }
    for (const m of NODE_MUST_NOT) {
      check(`节点端不含「${m}」`, !node.menus.includes(m))
    }
    check('节点端落地页是工作台而非系统总览',
      !node.url.includes('/console') && !node.url.endsWith('/index'),
      node.url)
    check('两棵树确实不同',
      JSON.stringify(admin.menus) !== JSON.stringify(node.menus),
      `管理端 ${admin.menus.length} 项 / 节点端 ${node.menus.length} 项`)

    // 节点端自己的页面也要点得开
    let nodeBad = 0
    for (const href of [...new Set(node.hrefs)].slice(0, 20)) {
      await rpc('Page.navigate', { url: `${ORIGIN}${BASE}${href.startsWith('/') ? href : '/' + href}` })
      await sleep(1500)
      const st = await ev(`({ url: location.href, len: document.body.innerText.trim().length })`)
      if (st.url.includes('404') || st.url.includes('401') || st.len < 40) {
        nodeBad++
        check(`节点端可打开 ${href}`, false, `落到 ${st.url.includes('401') ? '401' : '404/空白'}`)
      }
    }
    check('节点端无死链', nodeBad === 0, nodeBad ? `${nodeBad} 个页面打不开` : '')
  }

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.pass)
  console.log(`总计 ${results.length} 项，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  if (failed.length) {
    console.log('\n失败项：')
    failed.forEach((f) => console.log(`  - ${f.name}${f.detail ? '  → ' + f.detail : ''}`))
  }
  process.exitCode = failed.length ? 1 : 0
} catch (err) {
  console.error('\n[ERROR]', err.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}