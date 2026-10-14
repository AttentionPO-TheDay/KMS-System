import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Real deployed UI, isolated browser/admin session, only the 11 non-destructive probes.
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const pending = new Map(), errors = []
let browser, socket, sequence = 0
async function rpc(method, params = {}) {
  const id = ++sequence
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)) }, 15000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const reply = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (reply.exceptionDetails) throw new Error(reply.exceptionDetails.text)
  return reply.result?.value
}
try {
  browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=9399', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-security-ui-'))}`, '--no-first-run', '--window-size=1680,1200', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i=0;i<60;i++) { try { target=(await (await fetch('http://127.0.0.1:9399/json')).json()).find(t=>t.type==='page'); if(target)break } catch {} await delay(200) }
  assert(target); socket=new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
  socket.addEventListener('message', event=>{
    const m=JSON.parse(event.data)
    if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
    const request=pending.get(m.id);if(!request)return
    pending.delete(m.id);clearTimeout(request.timer);m.error?request.reject(new Error(m.error.message)):request.resolve(m.result)
  })
  await rpc('Runtime.enable');await rpc('Page.enable')
  await rpc('Page.navigate',{url:'http://127.0.0.1:8088/updatedel/demo'});await delay(1800)
  assert.equal(await evaluate(`fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json()).then(b=>b.code)`),200)
  await rpc('Page.navigate',{url:'http://127.0.0.1:8088/acceptance/'});
  let loaded=false
  for(let i=0;i<100;i++){loaded=await evaluate(`document.querySelectorAll('.security-picker select').length===3`);if(loaded)break;await delay(200)}
  assert(loaded,'deployed criteria loaded')
  const counts=await evaluate(`[...document.querySelectorAll('.security-picker select')].map(e=>e.options.length-1)`)
  assert.deepEqual(counts,[3,3,5])
  assert(await evaluate(`[...document.querySelectorAll('.security-picker select')].every(e=>e.selectedIndex===0&&e.value==='')`),'all-test option visible by default')
  await evaluate(`(()=>{const s=document.querySelector('.security-picker select');s.value='generation-identity-injection';s.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await delay(100)
  assert(await evaluate(`document.body.innerText.includes('本次仅执行：伪造生成节点身份')&&document.body.innerText.includes('执行所选测试')`),'single selection updates expected result and action')
  await evaluate(`(()=>{const s=document.querySelector('.security-picker select');s.value='';s.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await delay(100)
  assert(await evaluate(`!document.body.innerText.includes('登录暴力破解')&&!document.body.innerText.includes('Grover 重复搜索')`))
  for(const title of ['密钥生成协议校验','抗量子生成协议安全','无密码会话与网络边界']) {
    assert(await evaluate(`(()=>{const a=[...document.querySelectorAll('article.execution-item')].find(e=>e.querySelector('h3')?.innerText===${JSON.stringify(title)});const b=a?.querySelector('button.btn-primary');if(!b||b.disabled)return false;b.click();return true})()`),title+' executable')
    let passed=false
    for(let i=0;i<120;i++) {
      passed=await evaluate(`(()=>{const a=[...document.querySelectorAll('article.execution-item')].find(e=>e.querySelector('h3')?.innerText===${JSON.stringify(title)});return a?.querySelector('.item-status')?.innerText==='已通过'&&!a.querySelector('button.btn-primary')?.disabled})()`)
      if(passed)break;await delay(300)
    }
    assert(passed,title+' all cases pass through UI')
  }
  assert.equal(errors.length,0,errors.join('; '))
  const shot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true})
  writeFileSync('.system-security-ui.png',Buffer.from(shot.data,'base64'))
  console.log('PASS: 正式验收页面 3/3/5 新选项、无旧密码测试、三个全部执行按钮与 11 项真实通过、无浏览器异常')
} finally {
  socket?.close();browser?.kill();for(const r of pending.values())clearTimeout(r.timer)
}
