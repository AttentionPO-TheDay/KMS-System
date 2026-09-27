/**
 * 登录管理端并截图，用于验证「分组菜单」是否按预期渲染。
 * 用法: node tools/shot-admin.mjs <cdpPort> <outPrefix>
 */
import { writeFileSync } from 'node:fs'

const [, , port, outPrefix] = process.argv
const base = `http://127.0.0.1:${port}`

const list = await (await fetch(`${base}/json/list`)).json()
const target = list.find((t) => t.type === 'page')
const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  }
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { resolve: res, reject: rej })
  ws.send(JSON.stringify({ id: i, method, params }))
})
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Page.enable'); await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })

const evalJs = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.value

// 1) 先到登录页，便于同源写 cookie
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/login' })
await new Promise((r) => setTimeout(r, 4000))

// 2) 用界面真实登录（关闭验证码后）
const loginResult = await evalJs(`(async () => {
  try {
    const res = await fetch('/lifecycle-api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'admin123' })
    });
    const j = await res.json();
    if (j.token) { document.cookie = 'Admin-Token=' + j.token + '; path=/'; }
    return { code: j.code, hasToken: !!j.token, msg: j.msg };
  } catch (e) { return { err: String(e) }; }
})()`)
console.log('登录:', JSON.stringify(loginResult))

// 3) 进入管理端首页
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/index' })
await new Promise((r) => setTimeout(r, 9000))

const menu = await evalJs(`(() => {
  const items = [...document.querySelectorAll('.sidebar-container .el-menu > li')];
  return items.map(li => ({
    top: (li.querySelector('.el-sub-menu__title span, :scope > a span, span') || {}).textContent || '',
    children: [...li.querySelectorAll('.el-menu-item span')].map(s => s.textContent.trim())
  }));
})()`)
console.log('侧边栏菜单:')
for (const m of menu) {
  console.log(`  - ${m.top.trim()}`)
  for (const c of m.children) console.log(`      · ${c}`)
}

let shot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(`${outPrefix}-admin.png`, Buffer.from(shot.data, 'base64'))
console.log('截图:', `${outPrefix}-admin.png`)

ws.close(); process.exit(0)