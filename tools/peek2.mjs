import { writeFileSync } from 'node:fs'
const [, , port] = process.argv
const base = `http://127.0.0.1:${port}`
const list = await (await fetch(`${base}/json/list`)).json()
const t = list.find((x) => x.type === 'page')
const ws = new WebSocket(t.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (ev) => { const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result) } })
const send = (method, params={}) => new Promise((res,rej)=>{ const i=++id; pending.set(i,{resolve:res,reject:rej}); ws.send(JSON.stringify({id:i,method,params})) })
await new Promise((r)=>ws.addEventListener('open',r,{once:true}))
await send('Page.enable'); await send('Network.enable'); await send('Runtime.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Network.clearBrowserCache')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
const evalJs = async (e) => (await send('Runtime.evaluate',{expression:e,returnByValue:true,awaitPromise:true})).result.value

// 先登录页写 cookie
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/login' })
await new Promise((r)=>setTimeout(r,4000))
console.log('登录:', JSON.stringify(await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'admin', password:'admin123' }) });
  const j = await res.json();
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/';
  return { code:j.code, hasToken:!!j.token };
})()`)))
// 硬跳转（带时间戳绕缓存）
await send('Page.navigate', { url: 'http://127.0.0.1/updatedel/index?nocache=' + Date.now() })
await new Promise((r)=>setTimeout(r,11000))
const txt = await evalJs(`(() => {
  const sb = document.querySelector('.sidebar-container');
  return sb ? sb.innerText : '(无侧边栏)';
})()`)
console.log('侧边栏:')
for (const line of String(txt).split('\n')) console.log('  ' + line)
const shot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(process.argv[3] || 'C:/Users/AllenR/AppData/Local/Temp/kms-sel/admin2.png', Buffer.from(shot.data,'base64'))
console.log('截图已保存')
ws.close(); process.exit(0)