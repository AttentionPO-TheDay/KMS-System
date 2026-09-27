/**
 * 探测 vue-router 的 base 拼接行为。
 * 直接读侧边栏 <a href> 的真实值，从而确定 router.push 里到底该不该带 /updatedel 前缀。
 * 用法: node tools/probe-router-base.mjs [cdpPort]
 */
const port = process.argv[2] || '9222'
const CDP = `http://127.0.0.1:${port}`

let target
try { target = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json() }
catch { target = await (await fetch(`${CDP}/json/new?about:blank`)).json() }

const ws = new WebSocket(target.webSocketDebuggerUrl)
let n = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  }
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++n; pending.set(i, { resolve: res, reject: rej })
  ws.send(JSON.stringify({ id: i, method, params }))
})
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
const evalJs = async (e) => {
  const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })
  return r.exceptionDetails ? { __err: r.exceptionDetails.exception?.description } : r.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const ORIGIN = 'http://127.0.0.1'

// ---------- admin (updatedel) ----------
await send('Page.navigate', { url: `${ORIGIN}/updatedel/login` })
await sleep(3500)
await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'admin', password:'admin123' }) })
  const j = await res.json()
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/'
  return j.code
})()`)
await send('Page.navigate', { url: `${ORIGIN}/updatedel/index` })
await sleep(9000)
// 展开全部分组，让子菜单渲染出来
await evalJs(`(async () => {
  for (let i=0;i<8;i++){
    const t=[...document.querySelectorAll('.sidebar-container .el-sub-menu__title')]
    t.forEach(x=>x.click())
    await new Promise(r=>setTimeout(r,350))
  }
  return true
})()`)
await sleep(1500)
const adminLinks = await evalJs(`(() => {
  const as=[...document.querySelectorAll('.sidebar-container a')]
  return as.map(a=>({ text:a.innerText.replace(/\\s+/g,' ').trim(), href:a.getAttribute('href'), pathname:new URL(a.href).pathname }))
     .filter(x=>x.href)
})()`)
console.log('=== updatedel 侧边栏 href ===')
for (const l of adminLinks) console.log(`  ${String(l.text).slice(0,18).padEnd(20)} href=${l.href}`)

console.log('  location.pathname =', await evalJs('location.pathname'))
console.log('  BASE_URL =', await evalJs(`document.querySelector('base')?.href || '(no <base>)'`))

// ---------- distribute ----------
await send('Page.navigate', { url: `${ORIGIN}/distribute/` })
await sleep(8000)
const distLinks = await evalJs(`(() => {
  const as=[...document.querySelectorAll('.sidebar-container a, .el-menu a')]
  return as.map(a=>({ text:a.innerText.replace(/\\s+/g,' ').trim(), href:a.getAttribute('href') })).filter(x=>x.href)
})()`)
console.log('\n=== distribute 侧边栏 href ===')
console.log('  location.pathname =', await evalJs('location.pathname'))
for (const l of distLinks) console.log(`  ${String(l.text).slice(0,18).padEnd(20)} href=${l.href}`)

ws.close()
process.exit(0)
