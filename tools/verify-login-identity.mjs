// 验证：单一登录入口的身份选择 + 严格校验
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const API = '/lifecycle-api'
const PORT = 9321
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const dir = mkdtempSync(join(tmpdir(), 'loginid-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on)
  ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e) => (await rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })).result?.value

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }

function captcha(uuid) {
  const raw = execFileSync('docker', ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`], { encoding: 'utf8' }).trim()
  return raw ? raw.replace(/^"(.*)"$/s, '$1') : ''
}

// ⚠️ 必须排除 radio/checkbox：`el-radio-button` 会渲染出 `<input type="radio">`，
//    混进来会把索引全部错位（实测：页面上共 6 个 input，
//    0/1/2 是身份页签的 radio，3 才是密码）。用 type 过滤比按下标取稳。
const TEXT_FIELDS = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`

// 通过界面把表单填好（用原生 setter + input 事件，Vue 才收得到）
const FILL = (user, pass, code) => `(() => {
  const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}
  const ins=${TEXT_FIELDS}
  if(ins.length<3) return -1
  set(ins[0],${JSON.stringify(user)}); set(ins[1],${JSON.stringify(pass)}); set(ins[2],${JSON.stringify(code)})
  return ins.length
})()`

const CLICK_TAB = (label) => `(() => {
  const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()===${JSON.stringify(label)})
  if(!b) return false
  b.querySelector('input').click(); b.click(); return true
})()`

const READ = `(() => {
  const hint=document.querySelector('.principal-hint')?.innerText.trim()||''
  const ph=${TEXT_FIELDS}.map(i=>i.placeholder)
  const btns=[...document.querySelectorAll('.principal-switch .el-radio-button')].map(b=>b.innerText.trim())
  // 只取 el-message（提示条）的文本，不要整页文本 ——
  // 整页里本来就含"管理员""节点"两个页签名，用整页 contains 判断会恒真（假阳性）
  const msgs=[...document.querySelectorAll('.el-message')].map(m=>m.innerText.trim())
  return {hint,ph,btns,msgs,url:location.pathname,body:document.body.innerText.slice(0,200)}
})()`

/** 提交登录（点按钮），返回是否点到了按钮 */
const SUBMIT = `(() => {
  const btn=[...document.querySelectorAll('.login-form button')].find(b=>b.innerText.includes('登'))
  if(!btn) return false
  btn.click(); return true
})()`

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up yet */ }
    if (!t) await sleep(500)
  }
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable')

  console.log('\n== 登录页身份页签 ==')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  const init = await ev(READ)
  check('页签为「管理员 / 节点」', JSON.stringify(init.btns) === JSON.stringify(['管理员', '节点']), init.btns.join('/'))
  check('管理员模式用户名占位是「账号」', init.ph[0] === '账号', init.ph[0])
  check('管理员模式提示文案', init.hint.includes('管理员'), init.hint.slice(0, 24))

  const okTab = await ev(CLICK_TAB('节点'))
  await sleep(700)
  const switched = await ev(READ)
  check('能切到节点页签', okTab === true)
  check('切节点后用户名占位变为「节点 ID」', switched.ph[0] === '节点 ID', switched.ph[0])
  check('切节点后提示文案随之变化', switched.hint.includes('节点 ID'), switched.hint.slice(0, 28))

  // ---- 关键场景：以「节点」身份登录 admin 账号，应被拒绝 ----
  console.log('\n== 身份严格校验：admin 账号以「节点」身份登录 ==')
  const cap = await ev(`fetch('${API}/captchaImage').then(r=>r.json())`)
  const filled = await ev(FILL('admin', 'admin123', captcha(cap.uuid)))
  check('表单已填入 3 个字段', filled === 3, `实际 ${filled}`)
  // uuid 由 getCode() 异步写入；上面 fetch 取的是**另一张**验证码，
  // 覆盖输入框的值之后必须让表单里的 uuid 与它一致，否则服务端校验必然失败。
  // 真实用户是"看到图 → 输入图上的字"，所以这里也要走同一条路：
  // 读页面当前那张图对应的 uuid（存在 Vue 状态里，界面取不到），
  // 于是改为重新取一张并同步写入 —— 由 LOGIN_BY_UI 统一处理。
  await ev(SUBMIT)
  await sleep(5000)
  const denied = await ev(READ)
  check('被拒后仍停在登录页', denied.url.includes('/login'), denied.url)
  // 断言提示条本身，而不是整页文本 —— 整页里页签就写着"管理员/节点"
  const denyMsg = (denied.msgs || []).join(' | ')
  check('提示条说明了身份不匹配',
    denyMsg.includes('该账号是') && denyMsg.includes('不能以'),
    denyMsg || '(没有出现提示条)')

  // ---- 对照：同样选「节点」，但账号本身就是节点 → 应当放行 ----
  console.log('\n== 对照：节点账号以「节点」身份登录 ==')
  const nodeUser = process.argv[2]
  if (!nodeUser) {
    console.log('  [SKIP] 未提供节点账号（重置后无节点）。传参 node tools/verify-login-identity.mjs <节点账号> 可补测')
  } else {
    await ev(CLICK_TAB('节点'))
    const cap2 = await ev(`fetch('${API}/captchaImage').then(r=>r.json())`)
    await ev(FILL(nodeUser, 'admin123', captcha(cap2.uuid)))
    await ev(SUBMIT)
    await sleep(6500)
    const landed = await ev(READ)
    check('节点以「节点」身份登录成功并落到节点端', !landed.url.includes('/login'), landed.url)
  }

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.p)
  console.log(`总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  process.exitCode = failed.length ? 1 : 0
} catch (e) {
  console.error('ERR', e.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}
