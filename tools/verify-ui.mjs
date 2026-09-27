/**
 * 验证用户前台与管理端的最终呈现。
 * 用法: node tools/verify-ui.mjs <cdpPort> <outDir>
 */
import { captchaFields } from './lib/captcha.mjs'
import { writeFileSync } from 'node:fs'

const [, , port, outDir] = process.argv
const base = `http://127.0.0.1:${port}`
const list = await (await fetch(`${base}/json/list`)).json()
const t = list.find((x) => x.type === 'page')
const ws = new WebSocket(t.webSocketDebuggerUrl)
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
await send('Page.enable'); await send('Network.enable'); await send('Runtime.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Network.clearBrowserCache')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false })
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result.value
const shot = async (name) => {
  const s = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(`${outDir}/${name}.png`, Buffer.from(s.data, 'base64'))
  console.log('  截图:', `${name}.png`)
}

// ---------------- 1. 管理端 ----------------
console.log('=== 管理端 ===')
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/login' })
await new Promise((r) => setTimeout(r, 4000))
console.log('  登录:', JSON.stringify(await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'admin', password:'admin123', ...${JSON.stringify(await captchaFields('http://127.0.0.1', '/lifecycle-api'))} }) });
  const j = await res.json();
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/';
  return { code:j.code };
})()`)))
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/index?t=' + Date.now() })
await new Promise((r) => setTimeout(r, 11000))
console.log('  侧边栏:', JSON.stringify(await evalJs(
  `(() => { const sb=document.querySelector('.sidebar-container'); return sb?sb.innerText.split('\\n'):[] })()`
)))
console.log('  页面标题:', await evalJs(`document.querySelector('.sidebar-title')?.textContent || '(无)'`))
await shot('admin-console')

// 展开「密钥管理」分组，验证子菜单
await evalJs(`(() => {
  const subs = [...document.querySelectorAll('.sidebar-container .el-sub-menu__title')];
  const target = subs.find(s => s.textContent.includes('密钥管理'));
  if (target) target.click();
  return !!target;
})()`)
await new Promise((r) => setTimeout(r, 2000))
console.log('  展开后:', JSON.stringify(await evalJs(
  `(() => { const sb=document.querySelector('.sidebar-container'); return sb?sb.innerText.split('\\n'):[] })()`
)))
await shot('admin-menu-expanded')

// ---------------- 2. 用户前台 ----------------
console.log('=== 用户前台 ===')
await send('Page.navigate', { url: 'http://127.0.0.1/user/login' })
await new Promise((r) => setTimeout(r, 4000))
console.log('  登录:', JSON.stringify(await evalJs(`(async () => {
  const res = await fetch('/generate-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'admin', password:'admin123', ...${JSON.stringify(await captchaFields('http://127.0.0.1', '/generate-api'))} }) });
  const j = await res.json();
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/';
  return { code:j.code };
})()`)))
await send('Page.navigate', { url: 'http://127.0.0.1/user/workbench?t=' + Date.now() })
await new Promise((r) => setTimeout(r, 12000))
console.log('  工作台卡片:', JSON.stringify(await evalJs(`(() => {
  const t = document.body.innerText;
  return t.split('\\n').filter(x=>x.trim()).slice(0, 22);
})()`)))
console.log('  管理端入口存在:', await evalJs(`!!document.querySelector('.admin-entry')`))
await shot('user-workbench')

ws.close(); process.exit(0)