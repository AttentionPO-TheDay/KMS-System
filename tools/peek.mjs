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
await send('Runtime.enable')
const evalJs = async (e) => (await send('Runtime.evaluate',{expression:e,returnByValue:true,awaitPromise:true})).result.value
const txt = await evalJs(`(() => {
  const sb = document.querySelector('.sidebar-container') || document.querySelector('aside');
  return { found: !!sb, cls: sb ? sb.className : null, text: sb ? sb.innerText : document.body.innerText.slice(0,1500) };
})()`)
console.log(JSON.stringify(txt, null, 1))
ws.close(); process.exit(0)