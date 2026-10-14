// Isolated browser checks. Synthetic metadata only; never contacts production services.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome=['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const fixture=`
export const unwrap=r=>r.data;
export default {get:async(path,{params}={})=>{
 window.__requests.push({path,params:{...params}});
 if(window.__offline)throw Error('TEST_ONLY 数据源连接失败');
 const total=window.__empty?0:321;
 const page=Math.min(Number(params.page)||1,Math.ceil(total/(Number(params.pageSize)||20))||1);
 const size=Number(params.pageSize)||20;
 const items=Array.from({length:Math.min(size,Math.max(0,total-(page-1)*size))},(_,i)=>({
  rowId:(page-1)*size+i+1,keyId:'TEST_ONLY_KEY_'+((page-1)*size+i+1),nodeId:'demo-0',algorithm:'FALCON_CL_V1',
  version:1,status:params.section==='pool'?'READY':params.section==='sessions'?'established':params.section==='distribution'?'success':params.section==='acceptance'?'0':'ACTIVE',
  createdAt:'2026-10-13T20:00:00',expiresAt:'2026-10-14T20:00:00',
  poolId:'TEST_ONLY_POOL',keyIndex:i,sourceNode:'demo-0',targetNode:'demo-1',receiverNode:'demo-1',
  wrappingAlgorithm:'gm_sm2',payloadAlgorithm:'sm4',sessionType:'gm_sm2',sessionId:'TEST_ONLY_SESSION_'+i,
  batchId:'TEST_ONLY_BATCH_'+i,distributionType:'cross',nodeSuccessCount:1,
  userName:'acceptance_user',keyName:'acceptance-load',chainStatus:'0',
  generationScheme:'KMS_SPLIT_FALCON_CL_V1',securityLevel:512,
  chainBinding:{status:'CONFIRMED',txId:'TEST_ONLY_PUBLIC_TX_HASH',blockHeight:20,transactionValid:true,metadataMatches:true}
 }));
 return {data:{items,total,page,pageSize:size,account:'acceptance_user',source:'TEST_ONLY 只读元数据',
 summary:{total,byStatus:{ACTIVE:321,READY:321,established:321,success:321,'0':321},byType:{SM2:120,FALCON_CL_V1:201},byRange:{cross:321},chainCounts:{'0':321}}}};
}};
`
let server,browser,socket,seq=0
const pending=new Map(),errors=[]
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))
function rpc(method,params={}){
 const id=++seq
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending.delete(id);reject(Error(method))},15000)
  pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))
 })
}
async function evaluate(expression){
 const r=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})
 assert(!r.exceptionDetails,r.exceptionDetails?.text);return r.result?.value
}
async function waitFor(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(100)}throw Error(expression)}
async function screenshot(name){await delay(400);const shot=await rpc('Page.captureScreenshot',{format:'png'});writeFileSync(name,Buffer.from(shot.data,'base64'))}
try{
 server=await createServer({server:{port:5194,strictPort:true},plugins:[{
  name:'isolated-admin-data',enforce:'pre',
  resolveId(id){if(/\/api\/pqkds\/http(?:\.js)?$/.test(id))return '\0test-admin-http'},
  load(id){if(id==='\0test-admin-http')return fixture},
  configureServer(instance){instance.middlewares.use('/admin-data-fixture',async(_req,res)=>{
   const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f4f6fa"><div id="app"></div><script type="module">
   import {createApp,h,ref} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';
   import Panel from '/src/views/securityMonitor/AdminDataPanel.vue';window.__requests=[];window.__offline=false;window.__empty=false;
   const section=ref('keys');window.__setSection=value=>section.value=value;
   createApp({render:()=>h(Panel,{section:section.value})}).use(ElementPlus).mount('#app');
   </script></body></html>`
   res.setHeader('Content-Type','text/html');res.end(await instance.transformIndexHtml('/admin-data-fixture',html))
  })}
 }]})
 await server.listen()
 browser=spawn(chrome,['--headless=new','--remote-debugging-port=9404',`--user-data-dir=${mkdtempSync(join(tmpdir(),'kms-admin-data-ui-'))}`,'--no-first-run','--window-size=1500,1000','about:blank'],{stdio:'ignore',windowsHide:true})
 let target
 for(let i=0;i<60;i++){try{target=(await(await fetch('http://127.0.0.1:9404/json')).json()).find(r=>r.type==='page');if(target)break}catch{}await delay(200)}
 assert(target);socket=new WebSocket(target.webSocketDebuggerUrl)
 await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
 socket.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
  const p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)})
 await rpc('Runtime.enable');await rpc('Page.enable')
 await rpc('Page.navigate',{url:'http://127.0.0.1:5194/admin-data-fixture'})
 await waitFor(`document.body.innerText.includes('匹配 321 条')`)
 assert.equal(await evaluate(`window.__requests[0].params.status`),'ACTIVE')
 assert(await evaluate(`document.body.innerText.includes('已上链')`))
 await waitFor(`Array.from(document.querySelectorAll('.records-table .el-tag')).every(e=>e.getBoundingClientRect().width>30 && e.getBoundingClientRect().height>15 && getComputedStyle(e).opacity==='1')`)
 await screenshot('.admin-data-keys-desktop.png')
 await evaluate(`document.querySelector('.el-table__expand-icon').click()`)
 await waitFor(`document.body.innerText.includes('TEST_ONLY_PUBLIC_TX_HASH')`)
 await evaluate(`document.querySelector('.el-pagination .btn-next').click()`)
 await waitFor(`window.__requests.at(-1).params.page===2 && document.querySelector('.result-bar').innerText.includes('321')`)
 assert.equal(await evaluate(`document.querySelectorAll('.el-table__body-wrapper tbody tr.el-table__row').length`),20)
 await evaluate(`[...document.querySelectorAll('button')].find(b=>b.innerText.includes('查看全部历史版本')).click()`)
 await waitFor(`window.__requests.at(-1).params.status===''`)
 await evaluate(`[...document.querySelectorAll('.el-tabs__item')].find(e=>e.innerText==='验收压测记录').click()`)
 await waitFor(`window.__requests.at(-1).params.section==='acceptance' && document.body.innerText.includes('验收专用')===false && document.body.innerText.includes('acceptance_user')`)
 await screenshot('.admin-data-acceptance-desktop.png')
 for(const section of ['pool','sessions','distribution']){
  await evaluate(`window.__setSection('${section}')`)
  await waitFor(`window.__requests.at(-1).params.section==='${section}' && document.body.innerText.includes('匹配 321 条')`)
  await screenshot(`.admin-data-${section}-desktop.png`)
 }
 // Viewport layout, empty/source-error distinction and retry, all without real writes.
 for(const width of [768,390]){
  await rpc('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390})
  await delay(200)
  assert(await evaluate(`document.documentElement.scrollWidth<=window.innerWidth+1`),`document overflow at ${width}`)
  await screenshot(`.admin-data-distribution-${width}.png`)
 }
 await evaluate(`window.__offline=true;[...document.querySelectorAll('button')].find(b=>b.innerText.includes('刷新数据')).click()`)
 await waitFor(`document.querySelector('.source-error')!==null`)
 assert(!await evaluate(`document.body.innerText.includes('匹配 0 条')`))
 assert(await evaluate(`document.querySelector('.range-strip')===null`))
 await screenshot('.admin-data-source-error.png')
 await evaluate(`window.__offline=false;window.__empty=true;document.querySelector('.source-error button').click()`)
 await waitFor(`document.querySelector('.empty-state')!==null && document.body.innerText.includes('匹配 0 条')`)
 assert.equal(errors.length,0,errors.join(';'))
 console.log('PASS: four admin pages, acceptance separation, real server-page requests, chain details, history toggle, desktop/tablet/mobile, source error and empty states; synthetic data only')
}finally{socket?.close();browser?.kill();await server?.close()}
