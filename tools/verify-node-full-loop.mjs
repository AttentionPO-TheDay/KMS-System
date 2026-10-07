// =============================================================================
// verify-node-full-loop.mjs —— 节点从创建到可用的**完整闭环**（走界面）
// -----------------------------------------------------------------------------
// 这是"基本功能"的收口测试，串起每一步且每一步都走真实界面：
//
//   管理员：建节点 → **在界面上看到激活凭证**（只显示一次）
//      ↓
//   节点：切身份 → 填节点名 + 凭证 → 激活
//      ↓
//   引导页：生成四套基础密钥 → 登记公钥 → 节点变 ACTIVE
//      ↓
//   退出 → 登录页出现该节点 → 点击免输入登录 → 进得去业务页
//
// 为什么必须走界面：接口测过的路径不代表用户走得通 ——
// 本轮就吃过一次亏（`listActivatedNodes` 读错 store、按钮 :disabled 绑了字符串，
// 两者都是接口测试发现不了、只有点界面才暴露的）。
//
// ⚠️ 本脚本会真的建节点、真的耗尽一张激活凭证。用完的节点留在库里，
//    名如 Node-E2E-XXXXXX，不想留可以事后在节点列表里删。
//
// 用法：node tools/verify-node-full-loop.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const API = '/lifecycle-api'
const PORT = 9381
const NODE_ID = `Node-E2E-${Date.now().toString(36).toUpperCase().slice(-6)}`
// (ip, port) 在服务端有唯一约束，固定端口会与既有节点撞车
const NODE_PORT = 9000 + Math.floor(Math.random() * 900)
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function captcha(uuid) {
  const raw = execFileSync('docker', ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`], { encoding: 'utf8' }).trim()
  return raw ? raw.replace(/^"(.*)"$/s, '$1') : ''
}

const dir = mkdtempSync(join(tmpdir(), 'fullloop-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
let pageCaptchaUuid = ''
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e, timeoutMs = 60000) => {
  const r = await Promise.race([
    rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true }),
    new Promise((_, j) => setTimeout(() => j(new Error('页面求值超时')), timeoutMs)),
  ])
  if (r.exceptionDetails) return { __err: r.exceptionDetails.exception?.description || r.exceptionDetails.text }
  return r.result?.value
}
const TEXT_INPUTS = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
const SET = `(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}`

/** 装上错误/提示钩子 —— ElMessage 3 秒就消失，事后查是查不到的 */
const INSTALL_HOOK = `(() => {
  window.__dbg = {errors: [], messages: []}
  window.addEventListener('error', e => window.__dbg.errors.push('error: ' + (e.message||'')))
  window.addEventListener('unhandledrejection', e => window.__dbg.errors.push('reject: ' + (e.reason?.message || String(e.reason))))
  new MutationObserver(() => {
    document.querySelectorAll('.el-message').forEach(m => {
      const t = m.innerText.trim()
      if (t && !window.__dbg.messages.includes(t)) window.__dbg.messages.push(t)
    })
  }).observe(document.body, {childList:true, subtree:true})
  return true
})()`

function hookCaptcha() {
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.method === 'Network.responseReceived' && /captchaImage/.test(m.params?.response?.url || '')) {
      rpc('Network.getResponseBody', { requestId: m.params.requestId })
        .then((r) => { try { pageCaptchaUuid = JSON.parse(r.body).uuid || '' } catch { /* 非 JSON */ } })
        .catch(() => { /* 响应体可能已被丢弃 */ })
    }
  })
}

async function loginAdmin() {
  pageCaptchaUuid = ''
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(4000)
  await ev(INSTALL_HOOK)
  await ev(`(() => { const set=${SET}; const ins=${TEXT_INPUTS}
    set(ins[0],'admin'); set(ins[1],'admin123'); set(ins[2],${JSON.stringify(captcha(pageCaptchaUuid))}); return true })()`)
  await sleep(400)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('登')); b.click(); return true })()`)
  await sleep(7000)
  return await ev(`location.pathname`)
}

async function switchToNodeTab() {
  await ev(`(() => {
    const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点')
    if(!b) return false; b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(1200)
}

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
  hookCaptcha()

  // ===== 1. 管理员登录 =====
  console.log('\n== 1. 管理员登录（界面）==')
  const adminPath = await loginAdmin()
  check('管理员登录后进站', !adminPath.includes('/login') && adminPath.includes('index'), adminPath)
  const adminToken = await ev(`document.cookie.match(/Admin-Token=([^;]+)/)?.[1] || ''`)

  // ===== 2. 在**节点管理界面**上建节点，拿到激活凭证 =====
  console.log(`\n== 2. 界面上建节点 ${NODE_ID} ==`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/nodegov/nodes` })
  await sleep(6000)
  await ev(INSTALL_HOOK)

  // 点「新建节点」按钮（按钮文案以页面为准，做多关键词匹配）
  const opened = await ev(`(() => {
    const b=[...document.querySelectorAll('button')].find(x=>/新建|新增|创建/.test(x.innerText))
    if (!b) return false; b.click(); return true })()`)
  check('节点管理页有「新建」入口', opened === true)
  await sleep(2500)

  // 在弹窗里填必填项。
  // ⚠️ 按 **label 文本**定位，不要按 placeholder ——
  //    `el-input-number`（端口）根本没有 placeholder，IP 的 placeholder 是
  //    "例如 127.0.0.13" 也不含 "IP" 字样，按 placeholder 匹配会静默漏填，
  //    然后被必填校验拦住，现象是"点了确定没反应"。
  const filled = await ev(`(() => {
    const set=${SET}
    const dlg=document.querySelector('.el-dialog')
    if(!dlg) return {ok:false, why:'no dialog'}
    // el-form-item 的结构：label 与控件同在一个 .el-form-item 里
    const itemByLabel=(re)=>{
      const items=[...dlg.querySelectorAll('.el-form-item')]
      return items.find(it=>{
        const lb=it.querySelector('.el-form-item__label')
        return lb && re.test(lb.innerText.trim())
      })
    }
    const control=(it)=> it ? it.querySelector('input, textarea') : null
    const setItem=(re,val)=>{ const c=control(itemByLabel(re)); if(!c) return false; set(c,val); return true }

    const r={}
    r.id   = setItem(/^节点ID$/, ${JSON.stringify(NODE_ID)})
    r.name = setItem(/^节点名称$/, ${JSON.stringify(NODE_ID)})
    r.ip   = setItem(/IP 地址|IP地址/, '127.0.0.1')
    r.port = setItem(/^端口$/, '${NODE_PORT}')
    return {ok: r.id && r.name && r.ip && r.port, filled:r,
            labels:[...dlg.querySelectorAll('.el-form-item__label')].map(e=>e.innerText.trim())}
  })()`)
  check('建节点表单已填必填项', filled?.ok === true, JSON.stringify(filled))

  // 提交
  await ev(`(() => {
    const dlg=document.querySelector('.el-dialog')
    const b=[...dlg.querySelectorAll('button')].find(x=>/确 定|确定|保 存|保存|提 交|提交/.test(x.innerText))
    if(!b) return false; b.click(); return true })()`)

  // 建节点要生成节点账号，且服务端会签发凭证 —— 给足时间
  console.log('  （建节点中，需等待服务端处理…）')
  await sleep(20000)

  // ⚠️ 激活凭证 2026-10-08 起**默认打码**（按密码展示）：直接读 `.code-text`
  //    拿到的是点阵，拿它去激活必然失败，而现象只是"激活被拒"。
  //    所以先断言"默认没露明文"，再点「显示」读原文。
  const maskedState = await ev(`(() => {
    const el=document.querySelector('.el-dialog .code-text')
    const btn=[...document.querySelectorAll('.el-dialog button')].find(x=>x.innerText.trim()==='显示')
    return el ? {text: el.innerText.trim(), masked: el.classList.contains('is-masked'), hasReveal: Boolean(btn)} : null
  })()`)
  check('激活凭证默认打码（按密码展示，不是明文）',
    Boolean(maskedState) && maskedState.masked === true && /^[•·*]+$/.test(maskedState.text) && maskedState.hasReveal,
    JSON.stringify(maskedState))
  if (maskedState?.hasReveal) {
    await ev(`(() => {
      const b=[...document.querySelectorAll('.el-dialog button')].find(x=>x.innerText.trim()==='显示')
      if(b) b.click(); return true })()`)
    await sleep(600)
  }

  const dialogState = await ev(`(() => {
    const msgs=[...document.querySelectorAll('.el-message')].map(m=>m.innerText.trim())
    const codes=[...document.querySelectorAll('.code-text')].map(e=>e.innerText.trim())
    const dlgTitle=[...document.querySelectorAll('.el-dialog__title')].map(e=>e.innerText.trim())
    const alerts=[...document.querySelectorAll('.el-alert__title')].map(e=>e.innerText.trim())
    return {msgs, codes, dlgTitle, alerts, path: location.pathname}
  })()`)
  const shownCode = (dialogState?.codes || []).find((c) => /^[A-Za-z0-9_-]{30,}$/.test(c)) || ''
  check('界面上弹出了激活凭证（点「显示」后现出原文）', Boolean(shownCode),
    shownCode ? `长度 ${shownCode.length}` : JSON.stringify(dialogState).slice(0, 220))
  check('凭证弹窗明确提示"只显示这一次"',
    (dialogState?.alerts || []).some((a) => /只显示这一次/.test(a))
    || (dialogState?.dlgTitle || []).some((a) => /激活凭证/.test(a)),
    JSON.stringify(dialogState?.alerts))

  if (!shownCode) throw new Error('界面没给出激活凭证，闭环断在此处')

  // ===== 3. 节点激活（界面）=====
  console.log('\n== 3. 节点激活（界面）==')
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  await ev(INSTALL_HOOK)
  await switchToNodeTab()
  await ev(`(() => { const set=${SET}; const ins=${TEXT_INPUTS}
    set(ins[0],${JSON.stringify(NODE_ID)}); set(ins[1],${JSON.stringify(shownCode)}); return true })()`)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活')); b.click(); return true })()`)
  await sleep(8000)
  const afterActivate = await ev(`location.pathname`)
  check('激活后进入初始化引导页', afterActivate.includes('node-init'), afterActivate)

  // ===== 4. 引导页完成四套密钥初始化（闭环里最容易断的一环）=====
  console.log('\n== 4. 初始化四套基础密钥（会走设备指纹比对）==')
  const beforeInit = await ev(`(() => ({
    buttons: [...document.querySelectorAll('button')].map(b=>b.innerText.replace(/\\s+/g,' ').trim()).filter(Boolean),
    texts: document.body.innerText.slice(0, 400)
  }))()`)
  console.log(`  引导页按钮: ${JSON.stringify(beforeInit?.buttons || [])}`)

  const started = await ev(`(() => {
    const b=[...document.querySelectorAll('button')].find(x=>/初始化|生成|开始/.test(x.innerText) && !x.disabled)
    if(!b) return {ok:false, all:[...document.querySelectorAll('button')].map(x=>x.innerText.trim())}
    b.click(); return {ok:true, label:b.innerText.replace(/\\s+/g,' ').trim()}
  })()`)
  check('引导页能开始初始化', started?.ok === true, JSON.stringify(started).slice(0, 160))

  // Falcon 占大头，整体约 15~25 秒；轮询到 120 秒为止。
  //
  // ⚠️ 判据必须问**服务端**（节点状态是不是 ACTIVE），不能拿页面文本正则去猜。
  //    上一版用 /初始化已完成|四套/ 匹配页面文本，结果页面的**描述文字**里就有
  //    "四套基础密钥"，第一轮就误判成完成 —— 而节点其实还是 PENDING_INIT。
  //    假阳性比漏报更糟：它让测试通过，却把真实的失败藏起来。
  const selfStatus = async () => {
    const r = await ev(`fetch('/pqkds-api/node-self/',{headers:{'Authorization':'Bearer ' + (document.cookie.match(/Admin-Token=([^;]+)/)?.[1]||'')}}).then(r=>r.json())`)
    return r?.data?.node?.status || ''
  }
  let status = ''
  let initErrs = ''
  let initMsgs = ''
  for (let i = 0; i < 60; i++) {
    await sleep(2000)
    status = await selfStatus()
    if (status === 'ACTIVE') break
    const dbg = await ev(`window.__dbg || {errors:[], messages:[]}`)
    initErrs = (dbg?.errors || []).join(' | ')
    // ⚠️ 失败原因是 **ElMessage**（`catch` 里 ElMessage.error），
    //    它记在 messages 里、**不是** errors —— 上一版只读 errors，
    //    于是"看不到任何错误"，白等了两分钟。
    initMsgs = (dbg?.messages || []).join(' | ')
    if (initErrs || initMsgs) break
  }

  const finalPage = await ev(`({body: document.body.innerText, msgs: [...document.querySelectorAll('.el-message')].map(m=>m.innerText.trim())})`)
  const initBody = String(finalPage?.body || '')
  const pageMsgs = (finalPage?.msgs || []).join(' | ')

  check('初始化过程中没有未捕获错误', !initErrs, initErrs.slice(0, 200))
  check('初始化没有报"设备不一致"（指纹比对通过）',
    !/设备不一致|与登记的不一致/.test(initBody + initMsgs + pageMsgs),
    (initBody + initMsgs + pageMsgs).slice(0, 200))
  check('节点初始化完成（服务端状态为 ACTIVE）', status === 'ACTIVE',
    `状态=${status || '未知'}${initMsgs || pageMsgs ? ' | 页面提示：' + (initMsgs || pageMsgs).slice(0, 200) : ''}`)

  // ⚠️ 关键一步：从引导页点「进入工作台」——必须是 **SPA 内跳转**，
  //    不能整页导航。整页导航会重新走守卫的完整流程并注册动态路由，
  //    从而**掩盖**真实的 bug：PENDING_INIT 分支在 registerDynamicRoutes()
  //    之前就 return 了，用户点按钮时 `/workbench` 从未 addRoute，
  //    落到 catch-all 404（2026-09-30 用户实测反馈，脚本当时没抓到）。
  const clickedWorkbench = await ev(`(() => {
    const b=[...document.querySelectorAll('button')].find(x=>/进入工作台/.test(x.innerText))
    if(!b) return {ok:false, buttons:[...document.querySelectorAll('button')].map(x=>x.innerText.trim())}
    b.click(); return {ok:true}
  })()`)
  check('引导页有「进入工作台」按钮', clickedWorkbench?.ok === true, JSON.stringify(clickedWorkbench).slice(0, 160))
  await sleep(4000)
  const afterSpaNav = await ev(`(() => ({
    path: location.pathname,
    // ⚠️ 判据用 **渲染出来的 404 页面的根元素**（.wscn-http404，见 views/error/404.vue），
    //    不要用「整页文本里是否有 404」那种判法：页面别处也可能出现该字样，
    //    会**误报**（2026-09-30 实测：页面明明正常显示工作台，却被判成失败）。
    //    注意本段在模板字符串里，注释中不能出现反引号。
    is404: !!document.querySelector('.wscn-http404'),
    is401: !!document.querySelector('.errPage-container'),
    body: document.body.innerText.slice(0, 120).replace(/\\s+/g,' ')
  }))()`)
  check('SPA 内点「进入工作台」不落 404',
    !afterSpaNav?.is404 && !afterSpaNav?.is401 && String(afterSpaNav?.path).includes('workbench'),
    `${afterSpaNav?.path} | ${afterSpaNav?.body}`)

  // ===== 5. 服务端确认节点已 ACTIVE =====
  console.log('\n== 5. 服务端状态 ==')
  const statusRes = await ev(`(async () => {
    const r = await fetch('${API}/getInfo', {headers:{'Authorization':'Bearer ' + (document.cookie.match(/Admin-Token=([^;]+)/)?.[1]||'')}})
    const j = await r.json()
    return {code:j.code, name:j.user?.userName, principal:j.user?.principalType}
  })()`)
  check('节点令牌仍是 NODE 主体', String(statusRes?.principal).toUpperCase() === 'NODE', JSON.stringify(statusRes))

  // 直接问服务端：节点端自助接口会给出该账号对应节点的公开状态
  const selfNode = await ev(`fetch('/pqkds-api/node-self/',{headers:{'Authorization':'Bearer ' + (document.cookie.match(/Admin-Token=([^;]+)/)?.[1]||'')}}).then(r=>r.json())`)
  const nodeStatus = selfNode?.data?.node?.status || ''
  const nodeFingerprint = selfNode?.data?.node?.keyDeviceId || ''
  check('服务端节点状态为 ACTIVE', nodeStatus === 'ACTIVE', JSON.stringify(nodeStatus))
  check('服务端登记了设备指纹（激活时写入）', Boolean(nodeFingerprint), nodeFingerprint ? `指纹 ${nodeFingerprint.slice(0, 12)}` : '（为空）')

  // ===== 6. 退出后免输入登录 =====
  console.log('\n== 6. 免输入登录并进入业务页 ==')
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  await ev(INSTALL_HOOK)
  await switchToNodeTab()

  const listed = await ev(`[...document.querySelectorAll('.activated-name')].map(e=>e.innerText.trim())`)
  check('登录页列出该节点', (listed || []).includes(NODE_ID), JSON.stringify(listed))

  await ev(`(() => { const b=[...document.querySelectorAll('.activated-item')].find(x=>x.innerText.includes(${JSON.stringify(NODE_ID)})); if(!b) return false; b.click(); return true })()`)
  await sleep(7000)
  const afterLogin = await ev(`location.pathname`)
  check('免输入登录成功（不再落回登录页）', !afterLogin.includes('/login'), afterLogin)

  // 进一个节点端业务页，确认菜单真的可用
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/workbench` })
  await sleep(5000)
  const workbench = await ev(`(() => ({
    path: location.pathname,
    len: document.body.innerText.trim().length,
    menus: [...document.querySelectorAll('.sidebar-container .menu-title')].map(e=>e.innerText.trim())
  }))()`)
  check('能打开节点端业务页（工作台）',
    (workbench?.len || 0) > 50 && !String(workbench?.path).includes('404'), `len=${workbench?.len}`)
  // ⚠️ 落地页（工作台）**按设计不显示侧边栏**，所以"侧边栏"那几条断言
  //    必须换到一个确实有侧边栏的节点页去验 —— 在这里验会得到空数组，
  //    看起来像"侧边栏没渲染出来"的故障，其实是被这个测试自己误解了。
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/selfzone/selfnode` })
  await sleep(5000)
  const nodePage = await ev(`(() => ({
    path: location.pathname,
    len: document.body.innerText.trim().length,
    menus: [...document.querySelectorAll('.sidebar-container .menu-title')].map(e=>e.innerText.trim())
  }))()`)
  check('能打开节点端业务页（当前节点）',
    (nodePage?.len || 0) > 50 && !String(nodePage?.path).includes('404'), `len=${nodePage?.len}`)
  check('节点端侧边栏可见',
    (nodePage?.menus || []).includes('工作台') && (nodePage?.menus || []).includes('密钥生成'),
    JSON.stringify((nodePage?.menus || []).slice(0, 8)))
  // 节点端侧边栏应当是**该子系统自己的**功能，不该混进管理端页面
  // （实测踩到过：节点登录后第一条是「总览仪表盘」，那是管理端的静态路由）
  check('节点端侧边栏不含管理端页面（仪表盘/监管分区）',
    !(nodePage?.menus || []).some((m) => /总览仪表盘|密钥生成监管|密钥更新与回收监管|密钥分发监管|节点管理|区块链存证|验收测试台/.test(m)),
    JSON.stringify(nodePage?.menus || []))

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.p)
  console.log(`总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  console.log(`\n本次使用的节点：${NODE_ID}`)
  process.exitCode = failed.length ? 1 : 0
} catch (e) {
  console.error('\n[ERROR]', e.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}
