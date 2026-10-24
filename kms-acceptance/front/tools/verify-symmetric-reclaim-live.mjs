// Real deployed workbench, own Demo session, fixed isolated SM4 fixture only.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const origin = process.env.KMS_DEMO_ORIGIN || 'https://10.112.125.22:8443'
const output = process.env.KMS_EVIDENCE_DIR || mkdtempSync(join(tmpdir(), 'kms-sm4-live-'))
const profile = mkdtempSync(join(tmpdir(), 'kms-sm4-browser-'))
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const browser = spawn(chrome, ['--headless=new', '--no-first-run', '--remote-debugging-port=9433',
  `--user-data-dir=${profile}`, '--window-size=1440,1100', 'about:blank'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let socket, seq = 0
const pending = new Map(), errors = []
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => reject(Error(method)), 15000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const data = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!data.exceptionDetails, JSON.stringify(data.exceptionDetails))
  return data.result?.value
}
async function waitFor(expression) {
  for (let i=0;i<450;i++) { if(await evaluate(expression)) return; await delay(200) }
  throw Error('Timed out: '+expression)
}
async function shot(name) {
  const data = await rpc('Page.captureScreenshot', { format:'png',captureBeyondViewport:true })
  writeFileSync(join(output,name),Buffer.from(data.data,'base64'))
}
try {
  let target
  for(let i=0;i<80&&!target;i++) {
    try { target=(await(await fetch('http://127.0.0.1:9433/json/list')).json()).find(r=>r.type==='page') } catch {}
    if(!target) await delay(100)
  }
  assert(target)
  socket=new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
  socket.addEventListener('message',event=>{
    const data=JSON.parse(event.data)
    if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text)
    const request=pending.get(data.id)
    if(request){pending.delete(data.id);clearTimeout(request.timer);data.error?request.reject(Error(JSON.stringify(data.error))):request.resolve(data.result)}
  })
  await rpc('Runtime.enable');await rpc('Page.enable')
  await rpc('Page.navigate',{url:origin+'/acceptance/#/load-test'})
  await waitFor(`location.origin===${JSON.stringify(origin)}&&document.readyState==='complete'`)
  await evaluate(`(async()=>{const initial=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const response=await fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',headers:{'Content-Type':'application/json',
    'X-Kms-Demo-Revision':String(initial.revision),'X-Kms-Demo-CSRF':initial.csrfToken},body:'{}'});
    if(!response.ok)throw Error('Administrator session failed')})()`)
  await rpc('Page.reload',{ignoreCache:true})
  await waitFor(`document.querySelector('[data-criterion-id="symmetric-reclaim"] button:not(:disabled)')`)
  await evaluate(`document.querySelector('[data-criterion-id="symmetric-reclaim"] button').click()`)
  await waitFor(`document.querySelector('[data-criterion-id="symmetric-reclaim"] .performance-result a')`)
  const result=await evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const runs=await(await fetch('/acceptance-api/runs',{headers:{'X-Kms-Demo-Revision':String(c.revision)}})).json();
    return runs.data.find(r=>r.scenarioId==='symmetric-reclaim-tps')})()`)
  const e=result.symmetricEvidence
  assert.equal(result.error||'','')
  assert.equal(e.injected,12000);assert.equal(e.reclaimed,12000);assert.equal(e.remaining,0)
  assert.equal(e.controlsPassed,4);assert.equal(e.cleanupComplete,true);assert.equal(e.materialVerified,true)
  assert.equal(result.summary.successfulRequestsPerSec,e.reclaimed*1000/e.elapsedMs)
  assert.equal(result.passedTps,result.summary.successfulRequestsPerSec>=10000)
  assert.equal(result.status,result.passedTps?'passed':'failed_threshold')
  assert.equal(result.metricCheck.passed,true)
  assert(await evaluate(`document.querySelector('[data-criterion-id="symmetric-reclaim"]').innerText.includes('条/秒')`))
  await shot('sm4-desktop.png')
  for(const width of [768,390]) {
    await rpc('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width===390})
    await delay(150)
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'overflow '+width)
    await shot('sm4-'+width+'.png')
  }
  await rpc('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false})
  await evaluate(`document.querySelector('[data-criterion-id="symmetric-reclaim"] .performance-result a').click()`)
  await waitFor(`document.body.innerText.includes(${JSON.stringify(result.id)})&&document.querySelector('.audit-tabs button[aria-pressed="true"]').innerText==='对称密钥回收'`)
  await evaluate(`[...document.querySelectorAll('tbody tr')].find(r=>r.innerText.includes(${JSON.stringify(result.id)})).querySelector('button').click()`)
  await waitFor(`document.querySelector('.details-panel tbody tr')`)
  assert(await evaluate(`document.body.innerText.includes('到期SM4样本')&&document.body.innerText.includes('已删除')`))
  await shot('sm4-snapshots.png')
  await evaluate(`const s=document.querySelector('.detail-filters select');s.value='CONTROL_PASSED';s.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('.detail-filters button').click()`)
  await waitFor(`document.querySelectorAll('.details-panel tbody tr').length===4&&document.body.innerText.includes('匹配 4 把')`)
  await shot('sm4-controls.png')
  assert.deepEqual(errors,[])
  writeFileSync(join(output,'run.json'),JSON.stringify(result,null,2))
  console.log(JSON.stringify({status:result.status,id:result.id,reclaimed:e.reclaimed,controls:e.controlsPassed,elapsedMs:e.elapsedMs,rate:result.summary.successfulRequestsPerSec,output}))
}catch(error){
  if(socket?.readyState===1){console.log(await evaluate('document.body.innerText.slice(0,1800)'));await shot('failure.png')}
  throw error
}finally{socket?.close();browser.kill()}
