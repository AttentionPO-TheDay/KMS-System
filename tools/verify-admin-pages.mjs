/**
 * 用法: node tools/verify-admin-pages.mjs [cdpPort] [outDir] [app]
 *       app = admin（默认，管理端 /updatedel） | user（用户前台 /user）
 *
 * 背景：之前排障只能靠用户截图，样本少且滞后。本脚本用 CDP 直接驱动无头 Chrome：
 *   1. 登录并写入 Admin-Token Cookie；
 *   2. 管理端：调 /lifecycle-api/getRouters 拿后端下发的真实菜单树（侧边栏的数据源）；
 *      用户前台：路由是**前端静态表**，不走 getRouters，故用下面的常量；
 *   3. 逐个导航到页面，收集
 *        - Runtime.exceptionThrown          未捕获异常（如 CHART_COLORS is not defined）
 *        - Runtime.consoleAPICalled error   业务里被 catch 后打印的 console.error
 *        - Log.entryAdded                   MIME / 404 等浏览器级报错
 *        - Network.responseReceived >= 400  接口或静态资源失败
 *   4. 输出每页结论，任何一页有错即以退出码 1 结束。
 *
 * 关键点：必须 Network.setCacheDisabled(true)。否则浏览器复用旧 index.html，
 * 测出来的是缓存里的旧版本，而不是当前镜像里的产物。
 *
 * 用户前台必须用**普通用户**登录（默认 yx）：D9 之后管理员登录用户前台会被
 * 路由守卫整页重定向到管理端，用 admin 跑会得到一屏"跳走了"的假结果。
 */
import { captchaFields } from './lib/captcha.mjs'
import { writeFileSync, mkdirSync } from 'node:fs'

const port = process.argv[2] || '9222'
const outDir = process.argv[3] || 'kms-ops/tests/out'
const APP = (process.argv[4] || 'admin').toLowerCase()
const IS_USER_APP = APP === 'user'
mkdirSync(outDir, { recursive: true })

const CDP = `http://127.0.0.1:${port}`
const ORIGIN = 'http://127.0.0.1'
const BASE = IS_USER_APP ? '/user' : '/updatedel'

/**
 * 内容区最小文本量。低于它视为「白屏」。
 *
 * 取 20 是经验值：正常页面内容区（表头、按钮、说明文字）远超这个数，
 * 而组件 setup 抛错时内容区基本为空。
 */
const MIN_CONTENT_CHARS = 20
// 管理员账号进不了用户前台（D9 会把他送去管理端），所以两边用不同身份
const LOGIN_USER = IS_USER_APP ? 'yx' : 'admin'
const LOGIN_PASS = 'admin123'

/**
 * 用户前台的路由表是前端静态定义的（kms-user/front/src/router/index.js），
 * 后端不下发菜单，所以这里手工列出。新增/删除用户侧页面时必须同步这里，
 * 否则巡检会漏测。
 *
 * `mustInclude` 是该页的**标志性文本**：页面必须真的含这些字，否则判失败。
 * 理由见 `visit()` 里那段注释 —— "渲染为空但没有 console error" 是真实发生过的盲区。
 */
const USER_ROUTES = [
  { name: '总览', path: '/workbench', mustInclude: ['工作台'] },
  { name: '非对称密钥生成', path: '/generate/index', mustInclude: ['算法名称'] },
  { name: '更新与回收', path: '/lifecycle/index', mustInclude: ['密钥'] },
  { name: '密钥分发', path: '/distribute/index', mustInclude: ['密钥分发', '接收节点'] },
  // P3 步骤 9 新增页；漏登记会让巡检看不见它（曾经就漏过一次）
  { name: '对称密钥查看', path: '/symmetric-keys/index', mustInclude: ['对称密钥查看', '我的对称密钥'] },
  { name: '我的操作日志', path: '/my-logs/index', mustInclude: ['日志'] },
  { name: '个人中心', path: '/user/profile', mustInclude: ['个人'] }
]

// ---------- 新建一个干净的标签页 ----------
let target
try {
  target = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json()
} catch {
  target = await (await fetch(`${CDP}/json/new?about:blank`)).json()
}
if (!target?.webSocketDebuggerUrl) throw new Error('无法新建 CDP 标签页: ' + JSON.stringify(target))

const ws = new WebSocket(target.webSocketDebuggerUrl)
let msgId = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id)
    pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  } else if (m.method) {
    onEvent(m.method, m.params)
  }
})
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const i = ++msgId
    pending.set(i, { resolve: res, reject: rej })
    ws.send(JSON.stringify({ id: i, method, params }))
  })
await new Promise((r) => ws.addEventListener('open', r, { once: true }))

// ---------- 事件采集 ----------
let bucket = []
let collecting = false
const seen = new Set()
const push = (kind, text) => {
  if (!collecting) return
  const key = kind + '|' + text
  if (seen.has(key)) return
  seen.add(key)
  bucket.push({ kind, text })
}

function onEvent(method, p) {
  if (method === 'Runtime.exceptionThrown') {
    const d = p.exceptionDetails
    const desc = d.exception?.description || d.text || '(unknown)'
    push('exception', desc.split('\n').slice(0, 3).join(' ⏎ '))
  } else if (method === 'Runtime.consoleAPICalled') {
    if (p.type !== 'error' && p.type !== 'warning') return
    const text = (p.args || [])
      .map((a) => a.description ?? a.value ?? a.type ?? '')
      .join(' ')
      .split('\n')[0]
    const where = p.stackTrace?.callFrames?.[0]
    push('console.' + p.type, text + (where ? `  @${where.url.split('/').pop()}:${where.lineNumber + 1}` : ''))
  } else if (method === 'Log.entryAdded') {
    const e = p.entry
    if (e.level !== 'error') return
    push('log', `${e.text}${e.url ? '  ' + e.url.split('/').slice(-2).join('/') : ''}`)
  } else if (method === 'Network.responseReceived') {
    const r = p.response
    if (r.status >= 400) push('http', `${r.status} ${r.url.replace(ORIGIN, '')}`)
  } else if (method === 'Network.loadingFailed') {
    if (p.blockedReason || p.canceled) return
    push('netfail', `${p.errorText} ${p.type}`)
  }
}

await send('Page.enable')
await send('Runtime.enable')
await send('Log.enable')
await send('Network.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Network.clearBrowserCache')
await send('Emulation.setDeviceMetricsOverride', {
  width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false
})

const evalJs = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval failed')
  return r.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const shot = async (name) => {
  const s = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(`${outDir}/${name}.png`, Buffer.from(s.data, 'base64'))
}

// ---------- 登录 ----------
console.log(`== 登录（app=${APP} base=${BASE} user=${LOGIN_USER}）==`)
await send('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
await sleep(3500)
const login = await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'${LOGIN_USER}', password:'${LOGIN_PASS}', ...${JSON.stringify(await captchaFields(ORIGIN))} }) })
  const j = await res.json()
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/'
  return { code: j.code, msg: j.msg || '', gotToken: !!j.token, token: j.token || '' }
})()`)
console.log('  ', JSON.stringify({ ...login, token: login.token ? '<len ' + login.token.length + '>' : '' }))
if (!login.gotToken) {
  console.log('  登录失败，后续页面都会跳到登录页，终止。')
  process.exit(1)
}

// ---------- 取页面清单 ----------
let routes = []
if (IS_USER_APP) {
  routes = USER_ROUTES
  console.log(`== 用户前台静态路由 ${routes.length} 个 ==`)
  for (const r of routes) console.log(`   - ${r.name}  ${r.path}`)
} else {
  // 必须显式带 Authorization 头：RuoYi 的 JwtAuthenticationTokenFilter 只读这个头，
  // 不读 Cookie（Cookie 是给前端 axios 拦截器取 token 用的）。
  // 早先漏了它，getRouters 返回 401，菜单树摊平后是 0 个叶子，巡检静默跑空。
  const routers = await evalJs(`(async () => {
    const r = await fetch('/lifecycle-api/getRouters', { headers: { Authorization: 'Bearer ${login.token}' } })
    const j = await r.json()
    return JSON.stringify({ code: j.code, data: j.data || j.rows || [] })
  })()`)
  const parsed = JSON.parse(routers)
  if (parsed.code !== 200) {
    console.log(`  getRouters 失败 code=${parsed.code}，无法枚举页面`)
    process.exit(1)
  }
  const tree = parsed.data

  // 把菜单树摊平成「可访问的叶子路径」
  const walk = (nodes, prefix) => {
    for (const n of nodes || []) {
      let p = n.path || ''
      if (!p) continue
      // 顶层目录的 path 形如 '/keymanage'，子菜单是相对的（'keyupdate'）
      const full = p.startsWith('/') ? p : `${prefix}/${p}`.replace(/\/+/g, '/')
      const kids = n.children || []
      if (kids.length) {
        walk(kids, full)
      } else {
        // 内嵌页的判据取自**菜单树本身**（`component === 'frame/index'`），
        // 而不是导航后 URL 上的 `?url=` —— 后者只在"从侧边栏点进去"时才存在，
        // 而本巡检是按 URL 直接导航的，于是那个判据**永远为假**、
        // 整条 iframe 断言根本不会执行（我第一版就是这么写的，等于加了段死代码）。
        routes.push({
          name: n.meta?.title || n.name || full,
          path: full,
          isFrame: n.component === 'frame/index'
        })
      }
    }
  }
  walk(tree, '')
  console.log(`== 菜单树叶节点 ${routes.length} 个 ==`)
  for (const r of routes) console.log(`   - ${r.name}  ${r.path}`)
}

// ---------- 逐页巡检 ----------
const results = []
const visit = async (label, path, mustInclude = [], isFrame = false) => {
  bucket = []
  seen.clear()
  collecting = true
  const url = `${ORIGIN}${BASE}${path}`
  await send('Page.navigate', { url })
  await sleep(4200)
  // 等懒加载 chunk 与首屏接口都落地
  await sleep(2500)
  const href = await evalJs('location.href')
  // 取**全文**而不只是首屏：标志性内容可能不在前几行
  const fullText = await evalJs('document.body ? document.body.innerText : ""')
  const bodyHead = fullText.split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 6).join(' | ')
  collecting = false
  const errors = bucket.filter((b) => b.kind !== 'console.warning')
  const warns = bucket.filter((b) => b.kind === 'console.warning')

  // 落到 404 兜底页本身就是失败，但它是"干净渲染"，不会产生任何被采集到的错误 ——
  // 早期版本只看 errors，于是把「路由写错、页面其实没打开」误报成 ok。
  // 这里用兜底页的固定文案判定；判定不成立时也只是漏报，不会误伤正常页面。
  const is404Page = /404错误|找不到网页|页面不存在/.test(bodyHead)
  if (is404Page) {
    errors.push({ kind: 'route', text: `落在 404 兜底页，说明该路由未匹配：${path}` })
  }

  // -------------------------------------------------------------------------
  // 「页面是不是真的有内容」断言
  // -------------------------------------------------------------------------
  // 为什么需要这一段：组件在 setup 阶段抛错时，Vue 会把错误吞掉，
  // 页面渲染为**空白但没有任何 console error**。此时上面所有检查都是干净的，
  // 巡检会爽快地报 ok —— 这个盲区真的发生过两次：
  //   1. 服务层响应形状没对齐 → 表格 0 行，页面空着；
  //   2. 一次区间删除误伤了 import 与状态声明 → setup 抛错，整页空白。
  // 所以除了"没报错"，还必须要求**标志性文本出现**。
  if (mustInclude.length) {
    const missing = mustInclude.filter((marker) => !fullText.includes(marker))
    if (missing.length) {
      errors.push({
        kind: 'content',
        text: `页面缺少标志性内容 ${JSON.stringify(missing)}（页面可能渲染为空或组件 setup 报错，`
          + `而这类失败**不会**产生 console error）。实际文本前 200 字：${fullText.replace(/\s+/g, ' ').slice(0, 200)}`
      })
    }
  } else if (isFrame) {
    // -----------------------------------------------------------------------
    // 内嵌页（frame 路由）：**必须真的渲染出 iframe**
    // -----------------------------------------------------------------------
    // 为什么单独判这一支：这类页面"坏掉"时内容区**不是空的** ——
    // 组件的兜底告警（"该菜单没有配置要嵌入的地址"）就有 34 个字符，
    // 也就是说**光看"内容区非空"根本拦不住配错地址的 frame 页**。
    // 这正是我上一轮给自己记下的那个缺陷：阈值定得再高也只是碰运气，
    // 这类路由的正确判据是"有没有 iframe"，而不是"有多少字"。
    const frameInfo = await evalJs(
      `(() => {
         const f = document.querySelector('.app-main iframe')
         return { count: document.querySelectorAll('.app-main iframe').length, src: f ? f.getAttribute('src') : '' }
       })()`
    )
    if (!frameInfo || frameInfo.count < 1) {
      errors.push({
        kind: 'content',
        text: `这是内嵌页（菜单 component=frame/index）但没有渲染出 iframe。`
          + `常见原因：菜单 query 写成了查询串而不是 JSON（应为 {"url":"..."}）、`
          + `或 component 没指向 frame/index。`
          + `注意：此类失败**不会**产生 console error，且内容区往往非空（有兜底告警），`
          + `所以只能靠"有没有 iframe"来判。`
      })
    } else if (!String(frameInfo.src || '').startsWith('/')) {
      errors.push({
        kind: 'content',
        text: `iframe 的 src 不是同源相对路径：${frameInfo.src}。frame 组件只应嵌入同源子应用。`
      })
    }
  } else {
    // 没有写明标志性文案、也不是内嵌页的路由（管理端菜单是后端动态下发的，
    // 没法给每页手工登记），退而求其次量**内容区**的文本量。
    //
    // 关键：量的是 `.app-main`（路由内容区）而**不是** document.body ——
    // 后者含侧边栏与顶栏，即使内容区整个白屏也有一大段导航文字，那样的检查等于没做。
    const contentLength = await evalJs(
      `(() => { const el = document.querySelector('.app-main'); return el ? el.innerText.trim().length : -1 })()`
    )
    if (contentLength >= 0 && contentLength < MIN_CONTENT_CHARS) {
      errors.push({
        kind: 'content',
        text: `内容区几乎是空的（.app-main 文本 ${contentLength} 字符 < 阈值 ${MIN_CONTENT_CHARS}）。`
          + `这类"白屏但无报错"的失败不会产生 console error，早期版本会把它误报成 ok。`
      })
    }
  }

  results.push({ label, path, href, errors, warns })
  const flag = errors.length ? 'FAIL' : 'ok  '
  console.log(`\n[${flag}] ${label}  ${path}`)
  console.log(`       href: ${href}`)
  console.log(`       首屏: ${bodyHead.slice(0, 150) || '(空)'}`)
  for (const e of errors) console.log(`       ✗ ${e.kind}: ${e.text.slice(0, 240)}`)
  for (const w of warns) console.log(`       ! ${w.text.slice(0, 160)}`)
  return { href, errors }
}

// 首页单独先测，它是 CHART_COLORS 事故的现场
await visit(IS_USER_APP ? '总览' : '总览仪表盘', IS_USER_APP ? '/workbench' : '/index')
await shot('page-index')

for (const r of routes) {
  // 首页已在上面测过，跳过避免重复（重复本身不算错，只是浪费时间）
  if (IS_USER_APP && r.path === '/workbench') continue
  await visit(r.name, r.path, r.mustInclude || [], Boolean(r.isFrame))
}
await shot('page-last')

if (IS_USER_APP) {
  // -------------------------------------------------------------------------
  // 用户前台专有断言（P1 的 D1 / D2 / D9）
  // -------------------------------------------------------------------------
  console.log('\n== 用户前台 P1 断言 ==')

  // P1-2：权限管理页已删除 → 该路径必须落到 404，而不是渲染出权限页面
  {
    bucket = []
    seen.clear()
    collecting = true
    await send('Page.navigate', { url: `${ORIGIN}${BASE}/permissions/index` })
    await sleep(3000)
    const text = await evalJs('document.body ? document.body.innerText : ""')
    collecting = false
    const is404 = /404|找不到|页面不存在/.test(text)
    results.push({ label: '权限管理页应已删除', path: '/permissions/index', href: '', errors: is404 ? [] : [{ kind: 'route', text: '权限管理页仍然可访问' }] })
    console.log(`   ${is404 ? 'ok  ' : 'FAIL'} /permissions/index → ${is404 ? '404（已删除）' : '仍然渲染了页面'}`)
  }

  // D9：管理员访问用户前台必须被整页重定向到管理端
  {
    const adminLogin = await evalJs(`(async () => {
      const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ username:'admin', password:'admin123', ...${JSON.stringify(await captchaFields(ORIGIN))} }) })
      const j = await res.json()
      if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/'
      return !!j.token
    })()`)
    if (adminLogin) {
      await send('Page.navigate', { url: `${ORIGIN}${BASE}/workbench` })
      await sleep(5000)
      const href = await evalJs('location.href')
      const redirected = href.includes('/updatedel')
      results.push({ label: 'D9 管理员应被送去管理端', path: '/workbench', href, errors: redirected ? [] : [{ kind: 'route', text: `管理员未被重定向，停在 ${href}` }] })
      console.log(`   ${redirected ? 'ok  ' : 'FAIL'} 管理员访问 /workbench → ${href}`)
    } else {
      console.log('   ! 管理员登录失败，跳过 D9 断言')
    }
  }

  const failedUser = results.filter((r) => r.errors.length)
  console.log('\n================ 汇总 ================')
  console.log(`巡检页面: ${results.length}   通过: ${results.length - failedUser.length}   失败: ${failedUser.length}`)
  for (const f of failedUser) console.log(`  FAIL ${f.label} ${f.path}`)
  ws.close()
  process.exit(failedUser.length ? 1 : 0)
}

// ---------- 隐藏详情路由（不在侧边栏，只能靠列表页跳转进入）----------
// 这些路由由 dynamicRoutes 提供，路径带 :id，必须用真实 id 才能验证页面真的渲染。
// 之前 dynamicRoutes 是空数组，点「分配用户」等入口会落到 catch-all 的 404 页，
// 而侧边栏巡检覆盖不到，所以单独测。
console.log('\n== 隐藏详情路由 ==')
const ids = JSON.parse(
  await evalJs(`(async () => {
    const h = { Authorization: 'Bearer ${login.token}' }
    const get = async (u) => { try { const r = await fetch(u, { headers: h }); const j = await r.json()
      return (j.rows && j.rows[0]) || (j.data && j.data[0]) || null } catch { return null } }
    const [u, role, dict] = await Promise.all([
      get('/lifecycle-api/system/user/list?pageNum=1&pageSize=1'),
      get('/lifecycle-api/system/role/list?pageNum=1&pageSize=1'),
      get('/lifecycle-api/system/dict/type/list?pageNum=1&pageSize=1')
    ])
    return JSON.stringify({
      userId: u && (u.userId ?? u.user_id), roleId: role && (role.roleId ?? role.role_id),
      dictId: dict && (dict.dictId ?? dict.dict_id)
    })
  })()`)
)
console.log('  取样 id:', JSON.stringify(ids))
const hidden = []
if (ids.userId) hidden.push({ label: '分配角色', path: `/system/user-auth/role/${ids.userId}` })
if (ids.roleId) hidden.push({ label: '分配用户', path: `/system/role-auth/user/${ids.roleId}` })
if (ids.dictId) hidden.push({ label: '字典数据', path: `/system/dict-data/index/${ids.dictId}` })

for (const h of hidden) {
  const { href, errors } = await visit(h.label + '(隐藏)', h.path)
  // 落到 404 页会体现为 URL 变成兜底路由或首屏出现 404 文案
  if (href.includes(h.path)) continue
  results[results.length - 1].errors.push({ kind: 'route', text: `未落在目标路径，实际 ${href}` })
  console.log(`       ✗ 未落在目标路径: ${href}`)
}

// ---------- 看板快捷入口的 URL 拼接 ----------
// router 的 base 已是 /updatedel/，若按钮再 push('/updatedel/xxx') 就会翻倍成
// /updatedel/updatedel/xxx（用户截图里就是这个现象）。这里点击实测。
console.log('\n== 看板快捷入口跳转实测 ==')
bucket = []
seen.clear()
collecting = true
await send('Page.navigate', { url: `${ORIGIN}${BASE}/index` })
await sleep(6500)
const clickProbe = await evalJs(`(async () => {
  const out = []
  const btns = [...document.querySelectorAll('.action-btn')]
  for (const b of btns) {
    const label = b.innerText.trim()
    const before = location.pathname
    b.click()
    await new Promise(r => setTimeout(r, 900))
    out.push({ label, href: location.pathname, doubled: location.pathname.includes('/updatedel/updatedel') })
    history.pushState({}, '', '${BASE}/index')
    await new Promise(r => setTimeout(r, 200))
    void before
  }
  return out
})()`)
collecting = false
for (const c of clickProbe) {
  console.log(`   ${c.doubled ? 'FAIL' : 'ok  '} ${c.label} -> ${c.href}`)
}

// ---------- 汇总 ----------
const failed = results.filter((r) => r.errors.length)
console.log('\n================ 汇总 ================')
console.log(`巡检页面: ${results.length}   通过: ${results.length - failed.length}   失败: ${failed.length}`)
for (const f of failed) console.log(`  FAIL ${f.label} ${f.path}`)
const doubled = clickProbe.filter((c) => c.doubled)
console.log(`看板快捷入口翻倍: ${doubled.length ? 'FAIL ' + doubled.map((d) => d.label).join(',') : '无'}`)

ws.close()
process.exit(failed.length || doubled.length ? 1 : 0)
