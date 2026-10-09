// Actual deployed UI read-only smoke. NO Demo session mutation, registration, initialization or cleanup.
// Browser interception rejects every non-GET/HEAD request, so this cannot modify shared fixtures.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const DEMO = 'http://127.0.0.1:8088'
const ORIGINAL = 'http://127.0.0.1'
const chromePath = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chromePath)
const port = 9398
const profile = mkdtempSync(join(tmpdir(), 'kms-readonly-entry-'))
const child = spawn(chromePath, [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--headless=new', '--no-first-run', '--window-size=1600,1000', 'about:blank'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let ws, seq=0
const pending = new Map()
const errors = [], rejectedWrites = [], apiReads = []
function rpc(method, params={}) {
  return new Promise((resolve,reject)=>{
    const id=++seq
    pending.set(id,{resolve,reject})
    ws.send(JSON.stringify({id,method,params}))
  })
}
async function ev(expression) {
  const response = await rpc('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true})
  if(response.exceptionDetails)throw new Error(JSON.stringify(response.exceptionDetails))
  return response.result?.value
}
async function wait(expression,label) {
  for(let i=0;i<120;i++) {if(await ev(expression))return;await delay(100)}
  throw new Error(`Timeout ${label}: ${await ev('document.body.innerText.slice(0,600)')}`)
}
async function goto(url) {await rpc('Page.navigate',{url})}
try {
  let target
  for(let i=0;i<60&&!target;i++) {
    try {target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(row=>row.type==='page')}
    catch { /* browser starting */ }
    if(!target)await delay(100)
  }
  assert(target)
  ws=new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}))
  ws.addEventListener('message',event=>{
    const message=JSON.parse(event.data)
    if(message.id) {
      const request=pending.get(message.id)
      if(!request)return
      pending.delete(message.id)
      message.error?request.reject(new Error(JSON.stringify(message.error))):request.resolve(message.result)
    } else if(message.method==='Fetch.requestPaused') {
      const {requestId,request}=message.params
      if(!['GET','HEAD'].includes(request.method)) {
        rejectedWrites.push({method:request.method,url:request.url})
        rpc('Fetch.failRequest',{requestId,errorReason:'BlockedByClient'}).catch(error=>errors.push(error.message))
      } else {
        if(request.url.includes('/demo-api/'))apiReads.push(request.url)
        rpc('Fetch.continueRequest',{requestId}).catch(error=>errors.push(error.message))
      }
    } else if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text)
  })
  await rpc('Runtime.enable');await rpc('Page.enable')
  await rpc('Fetch.enable',{patterns:[{urlPattern:'*'}]})
  await goto(`${DEMO}/demo`)
  await wait(`location.pathname==='/updatedel/demo'&&document.body.innerText.includes('缺少节点 ID')`,'real Demo resolver')
  assert.equal(await ev(`!!document.querySelector('input[type=password]')`),false)
  assert.equal(await ev(`!![...document.querySelectorAll('button')].find(b=>b.innerText==='管理控制台'&&!b.disabled)`),true)
  console.log('[PASS] real /demo gateway redirects to application and renders anonymous controlled entry without credentials')
  await goto(`${DEMO}/demo?nodeId=A%2FB`)
  await wait(`document.body.innerText.includes('ASCII')`,'client-only invalid node guard')
  console.log('[PASS] real invalid node ID shows explicit guard without issuing a session mutation')
  const cookies=(await rpc('Network.getCookies',{urls:[DEMO]})).cookies
  assert(!cookies.some(row=>row.name==='KMS-Demo-Session'))
  console.log('[PASS] read-only/invalid entry does not create a Demo cookie')
  for(const path of ['/demo','/updatedel/demo','/demo-api/lifecycle/demo/context']) {
    const response=await fetch(`${ORIGINAL}${path}`,{redirect:'manual'})
    assert.equal(response.status,404,`original gateway must reject ${path}`)
  }
  console.log('[PASS] actual original 80 gateway rejects Demo pages and context API')
  const clicked = await ev(`(()=>{const link=[...document.querySelectorAll('a')].find(a=>a.innerText.trim()==='返回独立运行入口');if(!link)return false;link.click();return true})()`)
  assert(clicked, 'the real Demo return link exists')
  await wait(`location.origin===${JSON.stringify(ORIGINAL)}&&document.body.innerText.includes('独立运行')&&!![...document.querySelectorAll('button')].find(b=>b.innerText==='节点登录')`,'actual return link reaches original standalone origin')
  console.log('[PASS] actual Demo return anchor changes origin to original port 80')
  console.log('[PASS] real original standalone navigation remains available')
  assert.deepEqual(rejectedWrites,[],'no shared-state writes were attempted')
  assert.deepEqual(errors,[],'no uncaught browser exceptions')
  assert(apiReads.length>=2)
  console.log(`[PASS] actual browser read-only smoke: ${apiReads.length} Demo GET reads, zero write attempts, zero uncaught exceptions`)
} finally {
  if(ws)ws.close()
  child.kill()
}
