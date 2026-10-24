import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const origin = process.env.KMS_DEMO_ORIGIN || 'https://10.112.125.22:8443'
const output = resolve(process.env.KMS_EVIDENCE_DIR || '../../output/evidence-display/browser')
mkdirSync(output, { recursive: true })
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const debugPort = Number(process.env.KMS_BROWSER_PORT || 9456)
const browser = spawn(chrome, ['--headless=new', '--no-first-run', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-evidence-browser-'))}`, '--window-size=1440,1100', 'about:blank'],
  { stdio: 'ignore', windowsHide: true })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let socket, seq = 0
const pending = new Map(), errors = []
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => { pending.delete(id); reject(Error(method)) }, 20000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const data = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!data.exceptionDetails, JSON.stringify(data.exceptionDetails))
  return data.result?.value
}
async function waitFor(expression, attempts = 240) {
  for (let i = 0; i < attempts; i++) { if (await evaluate(expression)) return; await delay(250) }
  throw Error('Timed out: ' + expression)
}
async function shot(name) {
  const data = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  writeFileSync(join(output, name), Buffer.from(data.data, 'base64'))
}
async function catalog() {
  return evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const r=await fetch('/acceptance-api/lattice',{headers:{'X-Kms-Demo-Revision':String(c.revision)}});
    if(!r.ok)throw Error('Read failed '+r.status);return(await r.json()).data})()`)
}
try {
  let target
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).find(r => r.type === 'page') } catch {}
    if (!target) await delay(100)
  }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const data = JSON.parse(event.data)
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text)
    const request = pending.get(data.id)
    if (request) {
      pending.delete(data.id); clearTimeout(request.timer)
      data.error ? request.reject(Error(JSON.stringify(data.error))) : request.resolve(data.result)
    }
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Page.navigate', { url: origin + '/acceptance/#/load-test' })
  await waitFor(`location.origin===${JSON.stringify(origin)}&&document.readyState==='complete'`)
  await evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;
    const r=await fetch('/demo-api/lifecycle/demo/context/admin',{method:'POST',headers:{'Content-Type':'application/json',
    'X-Kms-Demo-Revision':String(c.revision),'X-Kms-Demo-CSRF':c.csrfToken},body:'{}'});
    if(!r.ok||(await r.json()).code!==200)throw Error('Admin session failed')})()`)
  await rpc('Page.reload', { ignoreCache: true })
  await waitFor(`document.querySelectorAll('.lattice-entry nav a').length===3`)

  await waitFor(`document.querySelector('.node-measurement')`)
  const part=process.env.KMS_EVIDENCE_PART || 'all'
  let data={performance:[],security:[]}, quantum=[], coreCounts=[], calculationCount=0
  if(part!=='lattice'){
  console.log('Browser ready; executing acceptance scenarios and security groups')
  const selectors=part==='security'?['generation-attacks','quantum-attacks','network-attacks'].map(id=>`[data-criterion-id="${id}"] .btn-primary`):['.header-actions .btn-primary']
  for(const selector of selectors){
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`)
    await waitFor(`document.querySelector('.header-actions .btn-primary').disabled`)
    if(part!=='security'||selector.includes('quantum-attacks')){
      await waitFor(`document.querySelector('.execution-trace .live-stage')`)
      if(part==='security') assert.equal(await evaluate(`document.querySelectorAll('.security-result.running[data-case-id^="quantum-lwe-"] .terminal-line:not(.live-stage)').length`),0,'Do not show protocol preparation as quantum model execution')
      await evaluate(`document.querySelector('.execution-trace .live-stage').scrollIntoView({block:'center'})`)
      await shot('live-process.png')
    }
    await waitFor(`!document.querySelector('.header-actions .btn-primary').disabled`,1600)
  }
  data=await evaluate(`(async()=>{const c=(await(await fetch('/demo-api/lifecycle/demo/context')).json()).data;const h={'X-Kms-Demo-Revision':String(c.revision)};const r=await Promise.all(['/runs','/security/runs'].map(async p=>(await(await fetch('/acceptance-api'+p,{headers:h})).json()).data));return{performance:r[0],security:r[1]}})()`)
  writeFileSync(join(output,part==='security'?'security-runs.json':'actual-runs.json'), JSON.stringify(data,null,2))
  assert.equal(data.performance.length,part==='security'?0:5)
  assert.equal(data.security.length,13)
  quantum=data.security.filter(r=>r.quantumEvidence)
  assert.equal(quantum.length,3)
  assert.equal(new Set(quantum.map(r=>r.quantumEvidence.model)).size,3)
  assert(quantum.every(r=>r.verdict==='evaluated'&&r.passed===false))
  assert.equal(await evaluate(`document.querySelectorAll('.model-process').length`),3)
  assert.equal(await evaluate(`document.querySelectorAll('.quantum-evidence .cost-scroll tbody tr').length`),9)
  assert.equal(await evaluate(`new Set(Array.from(document.querySelectorAll('.security-result[data-case-id^="quantum-lwe-"] .terminal-line .log-message')).map(el=>el.textContent.match(/LWE\\.\\w+/)?.[0]).filter(Boolean)).size`),3)
  assert.equal(await evaluate(`document.querySelectorAll('.auxiliary-evidence[open], .raw-evidence[open]').length`),0)
  assert.equal(await evaluate(`document.querySelectorAll('.raw-requests, .auxiliary-evidence, .quantum-evidence details').length`),0)
  assert.equal(await evaluate(`document.querySelector('[data-criterion-id="quantum-attacks"] .item-status').textContent`),'仿真与评估完成')
  assert.equal(await evaluate(`document.body.innerText.includes('指标待核验')||document.body.innerText.includes('公共准备与完整请求记录')||document.body.innerText.includes('共用业务对照与完整记录')`),false)
  coreCounts=await evaluate(`Array.from(document.querySelectorAll('.security-result:not([data-case-id^="quantum-lwe-"]) .execution-trace')).map(el=>Array.from(el.querySelectorAll('.terminal-line .log-tag')).filter(e=>/\\[(CALL|BUILD|MUTATE|CHECK|TRANSPORT|ASSERT)\\]/.test(e.textContent)).length)`)
  assert.equal(coreCounts.length,10)
  // Each attack must expose a real construction, execution and assertion
  // sequence. The exact count is intentionally allowed to vary by attack.
  assert(coreCounts.every(n=>n>=3),'Missing observed construction or assertion operations: '+JSON.stringify(coreCounts))
  assert(new Set(coreCounts).size>=3,'Attacks should reflect their real differing operations: '+JSON.stringify(coreCounts))
  assert(new Set(data.security.filter(r=>!r.quantumEvidence).map(r=>r.probeSteps.length)).size>=3)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.security-result .execution-trace')).some(el=>/建立独立测试会话|进入测试节点|攻击前验证合法/.test(el.textContent))`),false)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.security-result[data-case-id^="quantum-lwe-"] .terminal-line .log-tag')).filter(e=>e.textContent.includes('[CALL]')).length`),12)
  assert.equal(await evaluate(`document.querySelectorAll('.security-result .terminal-viewport[role="log"]').length`),13)
  const terminalSizes=await evaluate(`Array.from(document.querySelectorAll('.security-result[data-case-id^="quantum-lwe-"] .terminal-viewport')).map(el=>el.querySelectorAll('.terminal-line').length)`)
  assert(new Set(terminalSizes).size>1,'Quantum model logs must include their differing returned cost fields')
  assert(await evaluate(`document.querySelector('.security-result[data-case-id="network-csrf"] .terminal-viewport').textContent.includes('替换 CSRF 请求头')`))
  const downloadDir=join(output,'downloads')
  mkdirSync(downloadDir,{recursive:true})
  await rpc('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloadDir})
  await evaluate(`document.querySelector('.security-result[data-case-id="network-csrf"] .terminal-titlebar button:nth-of-type(2)').click()`)
  for(let i=0;i<50&&!existsSync(join(downloadDir,'kms-execution.log'));i++) await delay(100)
  const exported=readFileSync(join(downloadDir,'kms-execution.log'),'utf8')
  assert(exported.includes('[MUTATE]')&&exported.includes('[ASSERT]')&&exported.includes('X-Kms-Demo-CSRF')&&exported.endsWith('kms> 执行记录结束'))
  for(const [id,name] of [['quantum-lwe-usvp','usvp'],['quantum-lwe-bdd','bdd'],['quantum-lwe-dual','dual'],['network-csrf','network']]){
    await evaluate(`document.querySelector('.security-result[data-case-id="${id}"]').scrollIntoView({block:'start'})`)
    await evaluate(`document.querySelector('.security-result[data-case-id="${id}"] .terminal-viewport').scrollTop=0`)
    await shot(name+'-desktop.png')
  }
  if(part!=='security') for(const id of ['symmetric-reclaim','key-update','abnormal-revoke','revoke-rate','certless-generation']){
    await evaluate(`document.querySelector('[data-criterion-id="${id}"]').scrollIntoView({block:'start'})`)
    await shot(id+'-desktop.png')
  }
  calculationCount=await evaluate(`document.querySelectorAll('.performance-result .calculation').length`)
  assert(part==='security'||calculationCount>=4, 'Missing metric formulas: '+calculationCount)
  if(part!=='security') assert.equal(await evaluate(`document.querySelectorAll('.performance-result .execution-trace').length`),5)
  for(const width of [768,390]){
    await rpc('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width===390})
    await delay(200)
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Main page overflow '+width)
    await evaluate(`document.querySelector('.security-result[data-case-id="quantum-lwe-bdd"]').scrollIntoView({block:'start'})`)
    await shot('bdd-'+width+'.png')
  }
  await rpc('Emulation.clearDeviceMetricsOverride')
  writeFileSync(join(output,part==='security'?'security-verification.json':'dashboard-verification.json'),JSON.stringify({verified:true,part:'dashboard',performance:data.performance.map(r=>({id:r.id,scenarioId:r.scenarioId,status:r.status})),securityCases:data.security.length,coreCounts,calculationCount,consoleErrors:errors},null,2))
  }
  const lattice=[]
  let generatedRoot,delegated
  if(!['dashboard','security'].includes(part))
  for(const id of ['offline-trapdoor','basis-delegation','parallel-sampling']){
    await evaluate(`location.hash='/lattice/${id}'`)
    await waitFor(`document.querySelector('#title-${id}')&&!document.querySelector('.loading-message')`)
    if(id==='basis-delegation'){
      const d=await catalog(),node=d.nodes.find(n=>n.kyberAvailable)
      assert(node)
      await evaluate(`(()=>{for(const [id,value] of [['root-id',${JSON.stringify(generatedRoot)}],['node-id',${JSON.stringify(node.id)}]]){const e=document.getElementById(id);e.value=value;e.dispatchEvent(new Event('change',{bubbles:true}))}})()`)
    }
    if(id==='parallel-sampling') await evaluate(`(()=>{const e=document.getElementById('preparation-id');e.value=${JSON.stringify(delegated)};e.dispatchEvent(new Event('change',{bubbles:true}))})()`)
    await waitFor(`document.querySelector('.execute-button')&&!document.querySelector('.execute-button').disabled`)
    await evaluate(`document.querySelector('.execute-button').click()`)
    await waitFor(`document.querySelector('.results-section .status.passed')&&!document.querySelector('.execute-button').disabled`)
    const row=(await catalog()).records.find(r=>r.caseId===id)
    assert(row?.passed)
    if(id==='offline-trapdoor') generatedRoot=row.preparation.id
    if(id==='basis-delegation'){assert.equal(row.preparation.parentId,generatedRoot);delegated=row.preparation.id}
    if(id==='parallel-sampling') assert.equal(row.preparation.id,delegated)
    writeFileSync(join(output,id+'.json'),JSON.stringify(row,null,2))
    assert(await evaluate(`document.querySelectorAll('.execution-trace .terminal-line').length>=4`))
    if(id==='parallel-sampling'){
      assert.equal(await evaluate(`document.querySelectorAll('.worker-span').length`),row.workerSpans.length)
      assert.equal(await evaluate(`document.querySelectorAll('.worker-row').length`),row.usedWorkers)
      assert.equal(await evaluate(`Array.from(document.querySelectorAll('.terminal-line .log-tag')).filter(e=>e.textContent.includes('[THREAD]')).length`),row.workerSpans.length)
      await evaluate(`document.querySelector('.worker-timeline').open=true`)
    }
    await evaluate(`document.querySelector('.terminal-viewport').scrollTop=0`)
    assert.equal(await evaluate(`document.querySelectorAll('.run-metadata[open]').length`),0)
    assert.equal(await evaluate(`document.querySelectorAll('.error-message').length`),0)
    await evaluate(`document.querySelector('.execution-trace').scrollIntoView({block:'start'})`)
    await shot(id+'.png')
    if(id==='parallel-sampling'){
      await evaluate(`document.querySelector('.worker-timeline').scrollIntoView({block:'start'})`)
      await shot('sampling-worker-timeline.png')
    }
    for(const width of [768,390]){
      await rpc('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width===390})
      await delay(150)
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Lattice overflow '+id+' '+width)
      await shot(id+'-'+width+'.png')
    }
    await rpc('Emulation.clearDeviceMetricsOverride')
    lattice.push(id)
  }
  assert.deepEqual(errors,[])
  const summary={verified:true,part,origin,performance:data.performance.map(r=>({id:r.id,scenarioId:r.scenarioId,status:r.status,error:r.error||'',hasEvidence:Boolean(r.symmetricEvidence||r.fixedUpdateEvidence||r.abnormalEvidence)})),security:data.security.map(r=>({caseId:r.caseId,status:r.status,verdict:r.verdict})),defaultAttackRequestCounts:coreCounts,quantumModels:quantum.map(r=>r.quantumEvidence.model),calculationCount,latticePages:lattice,responsiveWidths:[1440,768,390],consoleErrors:errors}
  writeFileSync(join(output,part==='lattice'?'lattice-verification.json':'verification.json'),JSON.stringify(summary,null,2))
  console.log(JSON.stringify(summary))
} catch (error) {
  if (socket?.readyState === 1) {
    console.log(await evaluate('document.body.innerText.slice(0,2200)'))
    await shot('failure.png')
  }
  throw error
} finally {
  socket?.close(); browser.kill()
  for (const request of pending.values()) clearTimeout(request.timer)
}
