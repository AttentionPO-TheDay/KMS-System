/**
 * 登录管理端并 dump 侧边栏的实际渲染内容（DOM 为准）。
 * 用法: node tools/dump-admin-sidebar.mjs <cdpPort>
 */
const [, , port] = process.argv
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
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result.value

await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/login' })
await new Promise((r) => setTimeout(r, 3500))
console.log('登录:', JSON.stringify(await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'admin', password:'admin123' }) });
  const j = await res.json();
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/';
  return { code:j.code, hasToken:!!j.token };
})()`)))

// 强制无缓存重新进入
await send('Network.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/index?t=' + Date.now() })
await new Promise((r) => setTimeout(r, 10000))

const dump = await evalJs(`(() => {
  const sb = document.querySelector('.sidebar-container');
  if (!sb) return { error: '未找到 .sidebar-container' };
  const out = [];
  sb.querySelectorAll('.el-menu > li').forEach(li => {
    const isSub = li.classList.contains('el-sub-menu');
    const titleEl = li.querySelector('.el-sub-menu__title, .el-menu-item');
    const title = titleEl ? titleEl.textContent.trim() : '';
    const kids = [...li.querySelectorAll('.el-menu-item')].map(k => k.textContent.trim());
    out.push({ type: isSub ? '分组' : '单项', title, kids });
  });
  return { count: out.length, items: out };
})()`)
console.log('侧边栏 DOM:')
console.log(JSON.stringify(dump, null, 1))

ws.close(); process.exit(0)
