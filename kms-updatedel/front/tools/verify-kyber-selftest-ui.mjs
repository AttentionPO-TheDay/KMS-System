/**
 * KMS 缺陷验证（2026-10-04「自检报 i is not defined」）的**完整 UI 驱动**：
 * 在真浏览器里复刻用户走过的每一步，验证修复之后整条路径都能走通。
 *
 *   管理员建节点 → 登录页「节点」模式 + 激活凭证 → 激活并登录
 *   → 守卫落到「节点首次初始化」→ 点「开始初始化」（四套密钥本机生成）
 *   → 进「生成密钥」页 → 点 **Kyber 卡片的「自检」按钮** ← 用户报错的那一下
 *   → 断言卡片上出现「自检通过」且说明是 Kyber-768 往返一致
 *
 * ⚠️ 修好之前，最后一步会显示「自检未过：自检失败：i is not defined」
 *    （严格模式 + 该包 indcpa_enc 里的裸变量循环）—— 这个脚本就是它的回归判据。
 * ⚠️ 会真建节点、真生成密钥（浏览器 IndexedDB 真实落库），结尾自建自清。
 */
import { spawn, execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from '../../../tools/lib/captcha.mjs'
import { dockerBin } from '../../../tools/lib/mysql.mjs'

const ORIGIN = 'http://127.0.0.1'
const PQKDS = `${ORIGIN}/pqkds-api/pqkds`
const DOMAIN = 'kms-ui-kyber'

const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find(existsSync)
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
const check = (name, pass, detail = '') => {
  results.push({ name, pass })
  console.log(`  ${pass ? '[PASS]' : '[FAIL]'} ${name}${detail ? `  → ${detail}` : ''}`)
}

// ---- 1) 管理员建节点（直接调接口，不在驱动进程里加载前端模块）----
const adminToken = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
const seed = Date.now().toString(36).toUpperCase().slice(-6)
const nodeId = `KUI-${seed}`
const reg = await fetch(`${PQKDS}/nodes/register/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}` },
  body: JSON.stringify({
    node_id: nodeId, name: `UI 驱动节点 ${nodeId}`,
    ip_address: `10.77.${(Date.now() % 200) + 20}.1`, port: 62000 + (Date.now() % 2000),
    node_type: 'full', permission_level: 'L2', domain_id: DOMAIN
  })
}).then((r) => r.json())
const activationCode = reg?.data?.activation_code
check('管理员建节点成功并拿到激活凭证', Boolean(activationCode),
  `nodeId=${nodeId} code=${reg?.code}`)
if (!activationCode) { process.exit(1) }

// ---- 2) 起 CDP 浏览器 ----
const PORT = 9231
const dir = mkdtempSync(join(tmpdir(), 'kms-ui-kyber-'))
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'
], { stdio: 'ignore' })

let ws = null
for (let i = 0; i < 40 && !ws; i++) {
  try {
    const tabs = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
    const page = tabs.find((t) => t.type === 'page')
    if (page?.webSocketDebuggerUrl) ws = page.webSocketDebuggerUrl
  } catch { /* 还没起来 */ }
  if (!ws) await sleep(250)
}
if (!ws) { console.log('CDP 未就绪'); process.exit(1) }

const sock = new WebSocket(ws)
let id = 0
const pending = new Map()
sock.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
})
await new Promise((r) => sock.addEventListener('open', r, { once: true }))
const send = (method, params = {}) => new Promise((r) => {
  const myId = ++id
  pending.set(myId, r)
  sock.send(JSON.stringify({ id: myId, method, params }))
})
await send('Page.enable')
await send('Runtime.enable')

const evalJs = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (r?.result?.exceptionDetails) {
    return { __exception: r.result.exceptionDetails.exception?.description || '异常' }
  }
  return r?.result?.result?.value
}
const bodyText = () => evalJs('document.body ? document.body.innerText : ""')

/** 在页面里按文本点按钮/单选框（Vue 的 v-model 依赖真实事件，用 .click()）。 */
const clickByText = (selector, text) => evalJs(`
  (() => {
    const els = [...document.querySelectorAll(${JSON.stringify(selector)})]
    const el = els.find((e) => (e.innerText || '').trim().includes(${JSON.stringify(text)}))
    if (!el) return 'NOT_FOUND:' + els.length
    el.click()
    return 'CLICKED'
  })()
`)

/**
 * 等按钮**可用**再点（最多 `timeoutMs`）。
 *
 * ⚠️ 为什么不能直接 clickByText：按钮带 `:disabled="loading || !mapped"`，
 *    页面刚挂载时 load() 还没回来 —— 点一个禁用按钮是**静默无效**的
 *    （不报错、不触发 handler），现象是"点了但页面毫无反应"。
 *    独立页顶上那行品牌文案一进入就有"节点首次初始化"字样，用"等文字出现"
 *    当就绪条件更是**一进来就命中**（探测早于数据加载）。所以要等的是
 *    **disabled 变 false**，不是某个文案出现。
 */
const clickWhenEnabled = async (text, timeoutMs = 20000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutMs) {
    const state = await evalJs(`
      (() => {
        const btns = [...document.querySelectorAll('button')]
        const el = btns.find((b) => (b.innerText || '').includes(${JSON.stringify(text)}))
        if (!el) return 'NOT_FOUND'
        if (el.disabled) return 'DISABLED'
        el.click()
        return 'CLICKED'
      })()
    `)
    if (state === 'CLICKED') return state
    await sleep(400)
  }
  return 'TIMEOUT'
}
/** 给 el-input 填值：绕过 Vue 的包装，走原生 setter + input 事件。 */
const fillInput = (placeholder, value) => evalJs(`
  (() => {
    const el = [...document.querySelectorAll('input')]
      .find((i) => (i.placeholder || '').includes(${JSON.stringify(placeholder)}))
    if (!el) return 'NOT_FOUND'
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
    setter.call(el, ${JSON.stringify(value)})
    el.dispatchEvent(new Event('input', { bubbles: true }))
    return 'FILLED'
  })()
`)

/** 轮询页面文本直到命中/超时。返回 {hit, text}。 */
async function waitForText(substr, timeoutMs, label) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutMs) {
    const text = String(await bodyText() || '')
    if (text.includes(substr)) return { hit: true, text }
    await sleep(500)
  }
  return { hit: false, text: String(await bodyText() || '') }
}

// ---- 3) 登录页：切「节点」模式 → 填节点名 + 凭证 → 激活并登录 ----
await send('Page.navigate', { url: `${ORIGIN}/updatedel/login` })
await sleep(3000)
check('登录页已打开', String(await bodyText() || '').includes('登 录') || String(await bodyText() || '').includes('登录'))

const switchRadio = await clickByText('.principal-switch .el-radio-button', '节点')
check('已切到「节点」身份', switchRadio === 'CLICKED', String(switchRadio))
await sleep(800)
check('节点激活表单已出现（节点名 + 激活凭证）',
  (await fillInput('节点名称', nodeId)) === 'FILLED',
  '填入节点名')
check('填入一次性激活凭证', (await fillInput('激活凭证', activationCode)) === 'FILLED')

const activateClick = await clickByText('button', '激活并登录')
check('点击「激活并登录」', activateClick === 'CLICKED', String(activateClick))

// ---- 4) 守卫应把 PENDING_INIT 节点送到「节点首次初始化」 ----
const atInit = await waitForText('节点首次初始化', 20000)
check('★ 激活后守卫把未初始化节点送到「节点首次初始化」页',
  atInit.hit && String(await evalJs('location.pathname')).includes('/node-init'),
  `path=${await evalJs('location.pathname')}`)

// ★ 这页是**独立页面**（不经 Layout）：没有侧边栏/顶部菜单 ——
//   挂了完整导航会让人误以为"已经进系统了"，而这页是初始化未完成前的一道闸门。
const chromeOnInit = await evalJs(`
  (() => ({
    sidebar: Boolean(document.querySelector('.sidebar-container')),
    navbar: Boolean(document.querySelector('.navbar')),
    hasLogout: [...document.querySelectorAll('button')].some((b) => (b.innerText || '').includes('退出登录')),
  }))()
`)
check('★★ 「节点首次初始化」没有侧边栏（独立页面，不是系统内页）',
  chromeOnInit && chromeOnInit.sidebar === false,
  `sidebar=${chromeOnInit?.sidebar}`)
check('★ 也没有顶部菜单栏（连导航都不该出现）',
  chromeOnInit && chromeOnInit.navbar === false,
  `navbar=${chromeOnInit?.navbar}`)
check('★ 独立页面自带「退出登录」出口（没有导航也不至于走不掉）',
  chromeOnInit && chromeOnInit.hasLogout === true,
  `hasLogout=${chromeOnInit?.hasLogout}`)

// ---- 5) 点「开始初始化」：四套密钥本机生成并登记 ----
// ⚠️ 等按钮**可用**再点（页面刚挂载时它是禁用态，点了不生效，见 clickWhenEnabled）。
const initClick = await clickWhenEnabled('开始初始化')
check('点击「开始初始化」（等按钮从禁用变为可用后）', initClick === 'CLICKED', String(initClick))
const initDone = await waitForText('初始化已完成', 150000)
check('★★ 四套密钥（含 Kyber）本机生成 + 登记 + 收尾成功，节点转 ACTIVE',
  initDone.hit,
  initDone.hit
    ? '页面显示「初始化已完成」'
    : `超时。当前页文本片段：${initDone.text.replace(/\s+/g, ' ').slice(0, 200)}`)

// ---- 6) 生成页：点 Kyber 卡片的「自检」—— 用户报错的那一步 ----
await send('Page.navigate', { url: `${ORIGIN}/updatedel/genzone/create` })
await sleep(4000)
const genText = String(await bodyText() || '')
check('「生成密钥」页已打开且列出四张卡片',
  genText.includes('生成密钥') && genText.includes('Kyber'),
  genText.replace(/\s+/g, ' ').slice(0, 120))

/**
 * 对某算法的**卡片**做一次完整自检：点卡片里的「自检」→ 轮询该卡片文本直到
 * 出现结论（自检通过/未过）→ 未出现则重试（最多 3 轮）。
 *
 * ⚠️ 页面里「自检」按钮有**两处**：卡片一处、下方对照表的操作列一处。
 *    用"含算法名 + 带按钮的最小容器"去猜，会一路命中到包裹整页的容器、
 *    点到**表里的第一行**（实测就是这样点到 Falcon 的结论行上的）。
 *    所以这里用**精确类名**定位：
 *      * 卡片：`.gen-create__algo`（`v-for c in cards` 的那张）
 *      * 结果：`.gen-create__selftest`（卡片内的结论块）
 */
const selfTestCard = async (algo) => {
  const cardText = `
    (() => {
      const card = [...document.querySelectorAll('.gen-create__algo')]
        .find((el) => {
          const name = el.querySelector('.gen-create__algo-name')
          return name && (name.innerText || '').trim().toUpperCase() === ${JSON.stringify(algo.toUpperCase())}
        })
      if (!card) return ''
      const result = card.querySelector('.gen-create__selftest')
      return (result ? result.innerText : '') + '\\n' + card.innerText
    })()
  `
  const clickBtn = `
    (() => {
      const card = [...document.querySelectorAll('.gen-create__algo')]
        .find((el) => {
          const name = el.querySelector('.gen-create__algo-name')
          return name && (name.innerText || '').trim().toUpperCase() === ${JSON.stringify(algo.toUpperCase())}
        })
      if (!card) return 'NO_CARD'
      const btn = [...card.querySelectorAll('button')].find((b) => (b.innerText || '').trim() === '自检')
      if (!btn) return 'NO_BUTTON'
      if (btn.disabled) return 'DISABLED'
      btn.click()
      return 'CLICKED'
    })()
  `
  let clickR = ''
  let lastText = ''
  for (let attempt = 1; attempt <= 3; attempt++) {
    clickR = await evalJs(clickBtn)
    if (clickR === 'NO_CARD' || clickR === 'NO_BUTTON') break
    const t0 = Date.now()
    while (Date.now() - t0 < 8000) {
      const text = String(await evalJs(cardText) || '')
      lastText = text
      if (/自检(通过|未过)/.test(text)) return { click: clickR, text }
      await sleep(400)
    }
  }
  return { click: clickR || 'RETRIED', text: lastText }
}

// ---- 6a) Kyber：用户报错的那一下（先跑，独立断言便于定位）----
const kyberRun = await selfTestCard('Kyber')
const kyberLine = kyberRun.text.split('\n').map((l) => l.trim())
  .find((l) => /自检(通过|未过)/.test(l)) || ''
check('★★ Kyber 自检通过（修复前这里报「自检失败：i is not defined」）',
  /自检通过/.test(kyberLine) && /Kyber-768/.test(kyberLine),
  `${kyberRun.click} ${kyberLine.slice(0, 160) || `（诊断：卡片文本 ${kyberRun.text.replace(/\s+/g, ' ').slice(0, 150)}）`}`)
check('★ 自检结论与「i is not defined」无关（错误串不存在于页面上）',
  !kyberRun.text.includes('i is not defined'),
  kyberRun.text.includes('i is not defined') ? '页面上出现了该错误！' : '页面无该错误')

// ---- 6b) 其余三张卡（顺带覆盖）----
for (const algo of ['SM2', 'SSCL', 'Falcon']) {
  const run = await selfTestCard(algo)
  const line = run.text.split('\n').map((l) => l.trim())
    .find((l) => /自检(通过|未过)/.test(l)) || ''
  check(`${algo} 自检也通过（顺带覆盖）`,
    /自检通过/.test(line),
    `${run.click} ${line.slice(0, 130) || `（诊断：${run.text.replace(/\s+/g, ' ').slice(0, 140)}）`}`)
}

// ---- 6c) 状态文案：「可用」而不是「生产中」/「当前版本」 ----
// 判据用 **`.el-tag` 集合**而不是整页文本：页面上「可用于新会话」这类说明文案
// 也含"可用"二字，拿整页查会把"标签没换"放过去。
const tagTexts = String(await evalJs(
  `JSON.stringify([...document.querySelectorAll('.el-tag')].map((t) => (t.innerText || '').trim()))`
) || '')
const pageText6c = String(await bodyText() || '')
check('★★ ACTIVE 的展示文案是「可用」（"生产中"会被读成"正在生成"，'
  + '让人不敢用一把其实已就绪的密钥）',
  tagTexts.includes('"可用"') && !pageText6c.includes('生产中') && !pageText6c.includes('当前版本'),
  `el-tag 集合=${tagTexts.slice(0, 160)}`)

// ---- 6d) 设备字段：「绑定设备指纹」且如实说明不是 MAC ----
// ⚠️ 路由 = 目录菜单 + 子菜单：9474 `selfnode` 挂在 9430 `selfzone`（节点信息）下。
await send('Page.navigate', { url: `${ORIGIN}/updatedel/selfzone/selfnode` })
await sleep(4000)
const selfNodeText = String(await bodyText() || '')
check('★ 「当前节点」页的绑定设备字段标为「绑定设备指纹」'
  + '（原名"绑定设备"会让人以为是 MAC 地址）',
  selfNodeText.includes('绑定设备指纹'),
  selfNodeText.split('\n').map((l) => l.trim()).filter((l) => l.includes('绑定设备')).join(' | ').slice(0, 140) || '（页面片段：' + selfNodeText.replace(/\s+/g, ' ').slice(0, 120) + '）')
check('★ 页面上如实写明它是什么（设备公钥的 SHA-256 指纹，不是 MAC）',
  selfNodeText.includes('不是 MAC'),
  selfNodeText.split('\n').map((l) => l.trim()).find((l) => l.includes('MAC'))?.slice(0, 120) || '未找到说明行')

// ---- 7) 清理：删掉本脚本建的节点 ----
let cleanupOut = ''
try {
  cleanupOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
    input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d cascaded=%d left=%d' % (len(ids), deleted, left))
`,
    encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
  }).trim()
} catch (error) {
  cleanupOut = String(error?.stderr || error?.message || error)
}
console.log(`  [info] 清理：${cleanupOut}`)
check('清理完成：域内不再有本脚本建的节点', cleanupOut.endsWith('left=0'), cleanupOut)

try { proc.kill() } catch { /* 忽略 */ }

const passed = results.filter((r) => r.pass).length
console.log(`\n=== UI 驱动验证：${passed}/${results.length} 项通过 ===`)
if (passed !== results.length) process.exitCode = 1