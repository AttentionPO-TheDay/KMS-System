// Browser QA with synthetic responses only. Never connects to deployed APIs.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const fixture = `
export default ()=>({name:'测试节点',id:1,token:'fixture',roleLevel:2,sidebarRouters:[]});
export const IS_DEMO=true;
export const getDemoContext=()=>({principalType:'NODE',nodeId:'UI_ONLY'});
export const listDistributionBatches=async()=>({items:window.__mode==='zero'?[]:[{status:'success'},{status:'failed'}],total:window.__mode==='zero'?0:2});
export const getSelfWorkbench=async()=>{
 if(window.__mode==='error')throw Error('isolated failure');
 const zero=window.__mode==='zero';const total=zero?0:13;
 return {nodeId:'UI_ONLY',total,versionTotal:zero?0:18,active:zero?0:5,revoked:zero?0:2,
 algorithms:zero?{}:{SM2:4,SSCL:3,KYBER:3,FALCON:2,FALCON_CL_V1:1},
 statuses:zero?{}:{ACTIVE:5,RETIRED:6,REVOKED:2},chain:zero?{}:{confirmed:9,pending:2,failed:1,unregistered:1},
 trend:Array.from({length:7},(_,i)=>({date:'2026-10-'+(8+i),count:zero?0:[1,3,0,2,1,4,2][i]})),
 currentKeys:zero?[]:['SM2','SSCL','KYBER','FALCON','FALCON_CL_V1'].map(algorithm=>({algorithm,keyId:'test-'+algorithm+'-0123456789',keyVersion:2,statusLabel:'可用',allowsNewWork:true,versions:2,publicKeyHash:'fixture-hash',
 generation:{schemeId:algorithm==='KYBER'?'KMS_SPLIT_KEM_V1':algorithm==='FALCON'?'KMS_SPLIT_SIGN_V1':algorithm==='FALCON_CL_V1'?'KMS_SPLIT_FALCON_CL_V1':''}}))};
};`
let server, browser, socket, seq=0
const pending=new Map(),errors=[]
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))
function rpc(method,params={}) {return new Promise((resolve,reject)=>{
 const id=++seq,timer=setTimeout(()=>reject(Error(method)),15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))
})}
async function evaluate(expression) {const result=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result?.value}
async function waitFor(expression) {for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(100)}throw Error(expression)}
try {
 server=await createServer({server:{port:5195,strictPort:true,fs:{allow:[join(process.cwd(),'../..')]}},plugins:[{
 name:'isolated-workbench',enforce:'pre',
 resolveId(id){if(/\/(store\/modules\/(user|permission)|api\/pqkds\/node-self|services\/user-distribution-api|utils\/(entry-mode|demo-context))(\.js)?$/.test(id))return '\0workbench-fixture'},
 load(id){if(id==='\0workbench-fixture')return fixture},
 configureServer(instance){instance.middlewares.use('/workbench-fixture',async(_req,res)=>{
 const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="app"></div><script type="module">
 import {createApp} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';import '/src/assets/styles/index.scss';
 import {createRouter,createMemoryHistory} from 'vue-router';import Workbench from '/src/views/workbench/index.vue';
 window.__mode='normal';const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:Workbench}]});await router.push('/');await router.isReady();
 createApp(Workbench).use(router).use(ElementPlus).mount('#app');</script></body></html>`;
 res.setHeader('Content-Type','text/html');res.end(await instance.transformIndexHtml('/workbench-fixture',html));
 })}
 }]});await server.listen()
 browser=spawn(chrome,['--headless=new','--remote-debugging-port=9405',`--user-data-dir=${mkdtempSync(join(tmpdir(),'kms-workbench-'))}`,'--no-first-run','about:blank'],{stdio:'ignore',windowsHide:true})
 let target;for(let i=0;i<60;i++){try{target=(await(await fetch('http://127.0.0.1:9405/json')).json()).find(row=>row.type==='page');if(target)break}catch{}await delay(200)}assert(target)
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
 socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text);
 const request=pending.get(message.id);if(!request)return;pending.delete(message.id);clearTimeout(request.timer);message.error?request.reject(Error(JSON.stringify(message.error))):request.resolve(message.result)})
 await rpc('Runtime.enable');await rpc('Page.enable');await rpc('Page.navigate',{url:'http://127.0.0.1:5195/workbench-fixture'})
 await waitFor(`document.querySelectorAll('.chart-box canvas').length===5&&document.querySelector('.kpi-value')?.innerText==='13'`)
 for(const width of [1500,768,390]){
  await rpc('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});await evaluate(`window.dispatchEvent(new Event('resize'))`);await delay(500)
  const metrics=await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,charts:[...document.querySelectorAll('.chart-box')].map(e=>({width:e.clientWidth,height:e.clientHeight}))})`)
  assert(metrics.scroll<=metrics.width+1,JSON.stringify(metrics));assert(metrics.charts.every(row=>row.width>150&&row.height>200))
  if(width===1500){const rows=await evaluate(`[...document.querySelectorAll('.chart-box')].map(e=>Math.round(e.getBoundingClientRect().top))`);assert.equal(rows[0],rows[1]);assert.equal(rows[2],rows[3]);assert.equal(rows[3],rows[4])}
  const screenshot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync(`.workbench-${width}.png`,Buffer.from(screenshot.data,'base64'))
 }
 await evaluate(`window.__mode='zero';document.querySelector('.hero-actions button').click()`)
 await waitFor(`document.querySelector('.kpi-value')?.innerText==='0'&&document.querySelectorAll('.chart-notice').length===5`)
 assert.equal(await evaluate(`document.querySelectorAll('.is-unavailable').length`),0)
 let screenshot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync('.workbench-zero.png',Buffer.from(screenshot.data,'base64'))
 await evaluate(`window.__mode='error';document.querySelector('.hero-actions button').click()`)
 await waitFor(`document.querySelectorAll('.is-unavailable').length===4`)
 assert.equal(await evaluate(`document.querySelector('.kpi-value').innerText`),'-')
 assert(await evaluate(`document.body.innerText.includes('数据获取失败')`))
 await evaluate(`window.__mode='normal';document.querySelector('.hero-actions button').click()`)
 await waitFor(`document.querySelector('.kpi-value').innerText==='13'&&document.querySelectorAll('.is-unavailable').length===0`)
 assert.equal(errors.length,0,errors.join(';'))
 console.log('PASS: 工作台真实浏览器、1500/768/390px、五图布局、零数据、请求失败和刷新恢复；隔离数据')
} finally {socket?.close();browser?.kill();await server?.close()}
