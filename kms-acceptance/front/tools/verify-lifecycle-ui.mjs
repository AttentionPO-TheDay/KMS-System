// Real Vue app/browser; isolated synthetic metadata, never production requests.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome=['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
let server,browser,socket,seq=0
const pending=new Map(),errors=[],delay=ms=>new Promise(r=>setTimeout(r,ms))
function rpc(method,params={}) {const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(method)),15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,r.exceptionDetails?.text);return r.result?.value}
async function waitFor(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(100)}throw Error(expression)}
async function shot(name){await delay(400);const r=await rpc('Page.captureScreenshot',{format:'png'});writeFileSync(name,Buffer.from(r.data,'base64'))}
const bootstrap=`
window.__requests=[];window.__offline=false;window.__empty=false;
const originalFetch=window.fetch;
window.fetch=async(url,options)=>{
 if(String(url).startsWith('/demo-api/'))return new Response(JSON.stringify({code:200,data:{entryMode:'DEMO',principalType:'ADMIN',enabled:true,revision:1,csrfToken:'TEST_ONLY'}}));
 if(!String(url).startsWith('/acceptance-api'))return originalFetch(url,options);
 window.__requests.push(String(url));
 const u=new URL(url,location.origin),params=u.searchParams;
 if(u.pathname.includes('/acceptance/lifecycle')){
  if(window.__offline)return new Response(JSON.stringify({message:'TEST_ONLY 数据源不可用'}),{status:503});
  const scenario=params.get('scenario')||u.pathname.split('/').at(-1).replace('run-ui-','');
  const batch={id:'run-ui-'+scenario,scenarioId:scenario,startedAt:'2026-10-14T00:00:00+08:00',beforeAt:'2026-10-14T00:00:01+08:00',observedAt:'2026-10-14T00:00:12+08:00',status:'failed_threshold',account:'acceptance_user',poolSize:321,eligible:321,completed:300,pending:21,excluded:0,unknown:0,completionRate:300/321*100,successfulTps:6000,targetTps:5000,httpRequests:30000,httpErrors:1,socketErrors:2,threads:2,connections:50,durationSeconds:5,reason:'TEST_ONLY 使用验收专用密钥'};
  const size=Number(params.get('pageSize')||20),page=Number(params.get('page')||1);
  if(u.pathname==='/acceptance-api/acceptance/lifecycle')return new Response(JSON.stringify({items:window.__empty?[]:[batch],total:window.__empty?0:22,page,pageSize:size}));
  let rows=Array.from({length:321},(_,i)=>({keyId:i+1,before:{status:'0',version:1,exists:true},after:{status:i<300?'3':'0',version:scenario==='update-tps'&&i<300?2:1,exists:true,updatedAt:'2026-10-14 00:00:10'},outcome:i<300?'COMPLETED':'PENDING'}));
  if(params.get('outcome'))rows=rows.filter(r=>r.outcome===params.get('outcome'));
  if(params.get('q'))rows=rows.filter(r=>String(r.keyId).includes(params.get('q')));
  return new Response(JSON.stringify({batch,items:rows.slice((page-1)*size,page*size),total:rows.length,page,pageSize:size}));
 }
 return new Response(JSON.stringify({data:[]}));
};`
try{
 server=await createServer({server:{host:'127.0.0.1',port:5197,strictPort:true,fs:{allow:['../..']}}});await server.listen()
 assert((await fetch('http://127.0.0.1:5197/')).ok,'Vite must be reachable before browser checks')
 browser=spawn(chrome,['--headless=new','--remote-debugging-port=9417',`--user-data-dir=${mkdtempSync(join(tmpdir(),'kms-lifecycle-ui-'))}`,'--no-first-run','--window-size=1500,1000','about:blank'],{stdio:'ignore',windowsHide:true})
 let target;for(let i=0;i<60;i++){try{target=(await(await fetch('http://127.0.0.1:9417/json')).json()).find(r=>r.type==='page');if(target)break}catch{}await delay(200)}
 assert(target);socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener('open',r,{once:true}))
 socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);const p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)})
 await rpc('Runtime.enable');await rpc('Page.enable');await rpc('Page.addScriptToEvaluateOnNewDocument',{source:bootstrap})
 await rpc('Page.navigate',{url:'http://127.0.0.1:5197/#/lifecycle'})
 await waitFor(`document.body.innerText.includes('run-ui-update-tps')`)
 await evaluate(`document.querySelector('.text-button').click()`)
 await waitFor(`document.body.innerText.includes('匹配 321 把')`)
 assert(await evaluate(`document.body.innerText.includes('1 → 2')`))
 await shot('.lifecycle-update-desktop.png')
 await evaluate(`[...document.querySelectorAll('.details-panel .pager button')].find(b=>b.innerText==='下一页').click()`)
 await waitFor(`window.__requests.at(-1).includes('page=2') && document.querySelector('.details-panel tbody td').innerText==='21'`)
 await evaluate(`[...document.querySelectorAll('button')].find(b=>b.innerText==='查看仍未完成').click()`)
 await waitFor(`document.body.innerText.includes('匹配 21 把')`)
 assert(await evaluate(`window.__requests.at(-1).includes('outcome=PENDING')`))
 for(const scenario of ['revoke-tps','revoke-rate']){
  await evaluate(`[...document.querySelectorAll('.audit-tabs button')].find(b=>b.innerText==='${scenario==='revoke-tps'?'异常回收测试':'最终回收率'}').click()`)
  await waitFor(`document.body.innerText.includes('run-ui-${scenario}')`)
  await evaluate(`document.querySelector('.text-button').click()`)
  await waitFor(`document.body.innerText.includes('最终状态回收率')`)
  await shot(`.lifecycle-${scenario}-desktop.png`)
 }
 for(const width of [768,390]){
  await rpc('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390})
  await delay(300);assert(await evaluate(`document.documentElement.scrollWidth<=window.innerWidth+1`),`overflow ${width}`)
  await shot(`.lifecycle-${width}.png`)
 }
 await evaluate(`window.__offline=true;[...document.querySelectorAll('button')].find(b=>b.innerText==='刷新记录').click()`)
 await waitFor(`document.body.innerText.includes('TEST_ONLY 数据源不可用')`)
 assert(!await evaluate(`document.body.innerText.includes('尚无此类生命周期快照')`))
 await shot('.lifecycle-source-error.png')
 await evaluate(`window.__offline=false;window.__empty=true;document.querySelector('.audit-tabs button').click()`)
 await waitFor(`document.body.innerText.includes('尚无此类生命周期快照')`)
 assert.equal(errors.length,0,errors.join(';'))
 console.log('PASS: real Vue lifecycle page, three categories, immutable metadata display, server paging >200, pending filter, desktop/tablet/mobile, empty and error states; synthetic fixture only')
}catch(e){if(socket?.readyState===1){console.log(await evaluate(`({text:document.body.innerText.slice(0,1600),requests:window.__requests,errors:${JSON.stringify(errors)}})`));await shot('.lifecycle-test-failure.png')}throw e
}finally{socket?.close();browser?.kill();await server?.close()}
