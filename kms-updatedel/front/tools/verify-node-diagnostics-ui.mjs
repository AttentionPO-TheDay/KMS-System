// Isolated browser QA: fixtures never reach real business APIs.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
assert(existsSync(chrome))
const fixture = `
async function diagnostic(kind,id,version){
 window.__requests.push({kind,id,version});
 if(id==='slow')await new Promise(resolve=>window.__resolve=resolve);
 if(id==='missing')throw Error('未找到属于本节点的密钥或版本');
 return kind==='health'?{keyId:id,keyName:'KYBER',version:1,status:'ACTIVE',health:'OK',findings:[],observations:['公钥摘要一致']}:
 {baseInfo:{keyId:id,version:1,status:'ACTIVE'},affectedNodes:[{node_id:'PEER',name:'关联对端'}],operationTrails:[],distributeFootprints:[],affectedPoolItems:[]};
}
export const getOwnNodeKeyHealth=(id,version)=>diagnostic('health',id,version);
export const getOwnNodeKeyAnalysis=(id,version)=>diagnostic('analysis',id,version);
`
let legacy = ''
for (const path of ['src/api/lifecycle/lifecycle.js', 'src/api/pqkds/node-self.js']) {
 for (const match of readFileSync(path,'utf8').matchAll(/^export (?:async )?function (\w+)/gm)) {
  legacy += `export const ${match[1]}=async()=>{throw Error('Unexpected API: ${match[1]}')};\n`
 }
}
legacy += 'export const NODE_SELF_ERR={};'
let server,browser,socket,seq=0
const pending=new Map(),errors=[]
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))
function rpc(method,params={}){return new Promise((resolve,reject)=>{
 const id=++seq,timer=setTimeout(()=>reject(Error(method)),15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))
})}
async function evaluate(expression){const r=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value}
async function waitFor(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(100)}throw Error(expression+' '+JSON.stringify(await evaluate(`({requests:window.__requests,text:document.body.innerText.slice(0,1200)})`))+' '+errors.join(';'))}
async function input(value,index=0){await evaluate(`(()=>{const e=document.querySelectorAll('.${windowName}-query .el-input input')[${index}];e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}))})()`)}
let windowName='kh'
async function click(){await evaluate(`document.querySelector('.${windowName}-query button').click()`)}
async function navigate(page){await evaluate('window.__ready=false');await rpc('Page.navigate',{url:`http://127.0.0.1:5197/diagnostic-fixture?${page}`});await waitFor(`window.__ready===true&&location.search===${JSON.stringify('?'+page)}`)}
try{
 server=await createServer({server:{port:5197,strictPort:true,fs:{allow:[join(process.cwd(),'../..')]}},plugins:[{
  name:'isolated-diagnostics',enforce:'pre',
  resolveId(id){if(/\/api\/pqkds\/key-diagnostics(\.js)?$/.test(id))return '\0diagnostics';if(/\/api\/(lifecycle\/lifecycle|pqkds\/node-self)(\.js)?$/.test(id))return '\0legacy';if(/\/store\/modules\/user(\.js)?$/.test(id))return '\0user'},
  load(id){if(id==='\0diagnostics')return fixture;if(id==='\0legacy')return legacy;if(id==='\0user')return `export default()=>({principalType:'NODE'})`},
  configureServer(instance){instance.middlewares.use('/diagnostic-fixture',async(_req,res)=>{
   const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="app"></div><script type="module">
   import {createApp,h} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';import '/src/assets/styles/index.scss';
   import {createRouter,createMemoryHistory} from 'vue-router';import Health from '/src/views/keyHealth/index.vue';import Analysis from '/src/views/keyLeakAnalysis/index.vue';import Technical from '/src/components/TechnicalView/index.vue';
   window.__requests=[];const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:Health}]});await router.push('/');await router.isReady();
   createApp({render:()=>location.search.includes('technical')?h('div',{class:'app-container'},['preallocation','update','distribution'].map(kind=>h(Technical,{kind}))):h(location.search.includes('analysis')?Analysis:Health)}).use(router).use(ElementPlus).mount('#app');window.__ready=true;
   </script></body></html>`;res.setHeader('Content-Type','text/html');res.end(await instance.transformIndexHtml('/diagnostic-fixture',html));
  })}
 }]});await server.listen()
 browser=spawn(chrome,['--headless=new','--remote-debugging-port=9418',`--user-data-dir=${mkdtempSync(join(tmpdir(),'kms-diagnostics-'))}`,'--no-first-run','about:blank'],{stdio:'ignore',windowsHide:true})
 let target;for(let i=0;i<60;i++){try{target=(await(await fetch('http://127.0.0.1:9418/json')).json()).find(r=>r.type==='page');if(target)break}catch{}await delay(200)}assert(target)
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
 socket.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);const p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)})
 await rpc('Runtime.enable');await rpc('Page.enable')
 for(const page of ['health','analysis']){
  windowName=page==='health'?'kh':'la';await navigate(page)
  await input('diagnostic-KYBER');await delay(100)
  assert.equal(await evaluate('window.__requests.length'),0)
  assert(!await evaluate(`document.body.innerText.includes('全部检查通过')||document.body.innerText.includes('未发现关联痕迹')`))
  await click();await waitFor(`window.__requests.length===1&&document.body.innerText.includes(${JSON.stringify(page==='health'?'一致，未发现异常':'关联对端')})`)
  assert.equal((await evaluate('window.__requests[0]')).kind,page)
  await input('missing');await click();await waitFor(`document.body.innerText.includes('未找到属于本节点')`)
  assert(!await evaluate(`document.body.innerText.includes('全部检查通过')||document.body.innerText.includes('未发现关联痕迹')`))
  assert.equal(await evaluate(`document.querySelectorAll('.el-message,.el-notification').length`),0)
  await input('slow');await click();await waitFor(`Boolean(window.__resolve)`)
  await input('diagnostic-new');await click();await waitFor(`document.body.innerText.includes('diagnostic-new')`)
  await evaluate(`window.__resolve()`);await delay(100)
  assert(!await evaluate(`document.querySelector('.${windowName==='kh'?'kh-meta':'la-base'}').innerText.includes('slow')`))
  if(page==='health'){
   await input('123');await click();await waitFor(`window.__requests.at(-1).id==='123'`)
   assert.equal((await evaluate('window.__requests.at(-1)')).kind,'health')
  }else{
   const before=await evaluate('window.__requests.length');await input('-1',1);await click();await waitFor(`document.body.innerText.includes('版本须为正整数')`)
   assert.equal(await evaluate('window.__requests.length'),before)
  }
  await rpc('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:false});await delay(200)
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`))
  const shot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync(`.diagnostic-${page}-390.png`,Buffer.from(shot.data,'base64'))
 }
 await navigate('technical');await evaluate(`document.querySelectorAll('.el-collapse-item__header').forEach(e=>e.click())`)
 await waitFor(`document.body.innerText.includes('半诚实安全模型')`)
 for(const width of [1500,390]){
  await rpc('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});await delay(300)
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`))
  const shot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync(`.technical-${width}.png`,Buffer.from(shot.data,'base64'))
 }
 assert.equal(await evaluate('window.__requests.length'),0)
 assert.equal(errors.length,0,errors.join(';'))
 console.log('PASS: 点击才查询、节点字符串/数字ID分流、失败无假成功/弹框、晚到请求隔离、版本校验、手机布局、三种技术图解；无真实业务写入')
}finally{socket?.close();browser?.kill();await server?.close()}
