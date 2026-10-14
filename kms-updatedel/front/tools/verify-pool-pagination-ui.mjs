/** Formal deployment, isolated browser session, read-only pool verification. */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=9399',
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-pool-readonly-'))}`,
  '--no-first-run', '--window-size=1680,1100', 'about:blank'], { stdio: 'ignore', windowsHide: true })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const pending = new Map()
let socket, sequence = 0
async function rpc(method, params = {}) {
  const id = ++sequence
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(method)), 15000)
    pending.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
try {
  let target
  for (let i = 0; i < 60; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9399/json')).json()).find(t => t.type === 'page') } catch {}
    if (target) break
    await delay(200)
  }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const msg = JSON.parse(event.data), request = pending.get(msg.id)
    if (!request) return
    pending.delete(msg.id); clearTimeout(request.timer)
    msg.error ? request.reject(new Error(JSON.stringify(msg.error))) : request.resolve(msg.result)
  })
  await rpc('Page.navigate', { url: 'http://127.0.0.1:8088/updatedel/demo' })
  await delay(2500)
  const admin = await evaluate(`(async()=>{
    const ctx=(await (await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    return await (await fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',
      headers:{'Content-Type':'application/json','X-Kms-Demo-CSRF':ctx.csrfToken,'X-Kms-Demo-Revision':String(ctx.revision)},body:'{}'})).json();
  })()`)
  assert.equal(admin.code, 200)
  const results = await evaluate(`(async()=>{
    const pages=[];
    const ctx=(await (await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const headers={'X-Kms-Demo-CSRF':ctx.csrfToken,'X-Kms-Demo-Revision':String(ctx.revision)};
    for(const page of [1,21,30]) {
      const response=await (await fetch('/demo-api/pqkds/security-monitor/summary/?poolPage='+page+'&poolPageSize=10',{headers})).json();
      if(response.code!==200)throw new Error(response.msg);
      const pool=response.data.pool;
      pages.push({total:pool.total,page:pool.page,count:pool.items.length,ids:pool.items.map(i=>i.id)});
    }
    return pages;
  })()`)
  assert(results[0].total > 200, JSON.stringify(results))
  assert.equal(results[1].page, 21)
  assert.equal(results[1].count, 10)
  assert(!results[0].ids.some(id => results[1].ids.includes(id)))
  await rpc('Page.navigate', { url: 'http://127.0.0.1:8088/updatedel/demo/admin/admindata/pool' })
  let ready = false
  for (let i = 0; i < 80; i++) {
    ready = await evaluate(`document.querySelector('.sm-pagination .el-pagination__total')?.innerText.includes('${results[0].total}')`)
    if (ready) break
    await delay(250)
  }
  assert(ready, await evaluate('document.body.innerText.slice(0,800)'))
  const totalText = await evaluate(`document.querySelector('.sm-pagination .el-pagination__total').innerText`)
  assert(totalText.includes(String(results[0].total)), totalText)
  const firstRows = await evaluate(`document.querySelector('.sm-table').innerText`)
  await evaluate(`document.querySelector('.sm-pagination .el-pager li.number:last-child').click()`)
  const lastPage = Math.ceil(results[0].total / 10)
  for (let i = 0; i < 80; i++) {
    if (await evaluate(`document.querySelector('.sm-pagination .el-pager li.is-active')?.innerText === '${lastPage}'`)) break
    await delay(250)
  }
  assert.equal(await evaluate(`document.querySelector('.sm-pagination .el-pager li.is-active')?.innerText`), String(lastPage))
  assert.notEqual(await evaluate(`document.querySelector('.sm-table').innerText`), firstRows)
  console.log(JSON.stringify({ pass: true, totalText, lastPage, apiPages: results.map(({ ids, ...rest }) => rest), businessWrites: 0 }))
} finally {
  socket?.close(); browser.kill()
  for (const request of pending.values()) clearTimeout(request.timer)
}
