// 验证：单一登录入口的身份选择 + 节点激活凭证校验
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
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

// 只读取文本和密码字段，排除身份页签的 radio 与复选框。
const NODE_FIELDS = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
const FILL_NODE = (nodeId, activationCode) => `(() => {
  const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}
  const ins=${NODE_FIELDS}
  if(ins.length<2) return -1
  set(ins[0],${JSON.stringify(nodeId)}); set(ins[1],${JSON.stringify(activationCode)})
  return ins.length
})()`

const CLICK_TAB = (label) => `(() => {
  const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()===${JSON.stringify(label)})
  if(!b) return false
  b.querySelector('input').click(); b.click(); return true
})()`

const READ = `(() => {
  const hint=document.querySelector('.principal-hint')?.innerText.trim()||''
  const ph=${NODE_FIELDS}.map(i=>i.placeholder)
  const btns=[...document.querySelectorAll('.principal-switch .el-radio-button')].map(b=>b.innerText.trim())
  // 只取 el-message（提示条）的文本，不要整页文本 ——
  // 整页里本来就含"管理员""节点"两个页签名，用整页 contains 判断会恒真（假阳性）
  const msgs=[...document.querySelectorAll('.el-message')].map(m=>m.innerText.trim())
  return {hint,ph,btns,msgs,url:location.pathname,body:document.body.innerText.slice(0,200)}
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
  check('切节点后显示节点名称输入框', switched.ph[0].includes('节点名称'), switched.ph[0])
  check('切节点后显示一次性激活凭证输入框', switched.ph[1].includes('激活凭证'), switched.ph[1])
  check('切节点后提示文案说明激活凭证或免密登录', switched.hint.includes('激活凭证'), switched.hint.slice(0, 40))

  // ---- 节点身份：无效一次性凭证必须停留在登录页 ----
  console.log('\n== 节点身份：无效激活凭证应被拒绝 ==')
  const invalidNodeFilled = await ev(FILL_NODE('admin', 'invalid-activation-code'))
  check('节点表单已填入名称和激活凭证', invalidNodeFilled >= 2, `实际 ${invalidNodeFilled}`)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活并登录')); if(!b)return false;b.click();return true })()`)
  await sleep(1200)
  const invalidNode = await ev(READ)
  check('无效激活凭证被拒后仍停在登录页', invalidNode.url.includes('/login'), invalidNode.url)

  // ---- 对照：传入节点名称 + 一次性激活凭证才执行真实激活登录 ----
  console.log('\n== 对照：节点使用一次性激活凭证登录 ==')
  const nodeUser = process.argv[2]
  const activationCode = process.argv[3]
  if (!nodeUser || !activationCode) {
    console.log('  [SKIP] 未提供节点名称和一次性激活凭证；传参 node tools/verify-login-identity.mjs <节点名称> <激活凭证> 可补测')
  } else {
    await ev(FILL_NODE(nodeUser, activationCode))
    await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活并登录')); if(!b)return false;b.click();return true })()`)
    await sleep(6500)
    const landed = await ev(READ)
    check('节点凭证登录成功并落到节点端', !landed.url.includes('/login'), landed.url)
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
