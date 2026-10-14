// Browser QA with synthetic responses only. Never connects to deployed APIs.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
const fixture = `
const rows=[{id:1,node_id:'NODE-A',name:'甲节点',domain_id:'domain-1',status:'ACTIVE',permission_level:'L1'},{id:2,node_id:'NODE-B',name:'乙节点',domain_id:'domain-2',status:'ACTIVE',permission_level:'L2'}];
export const listAllNodes=async()=>{if(window.__mode==='error')throw Error('隔离接口失败');return rows.map(row=>({...row}))};
export const updateNode=async(id,payload)=>{window.__requests.push({id,payload});rows.find(row=>row.id===id).domain_id=payload.domain_id;return {}};
const domains=[{domain_id:'domain-1',name:'甲域'},{domain_id:'domain-2',name:'乙域'}];
export const listDomains=async()=>domains.map(row=>({...row}));
export const createDomain=async(payload)=>{if(domains.some(row=>row.domain_id===payload.domain_id))throw Error('该域标识已存在');domains.push(payload);window.__created=payload;return payload};
`
let nodeFixture = `
export const getSelfNode=async()=>({mapped:true,node:{nodeId:'SELF',domainId:'domain-1'}});
export const listNodeDirectory=async()=>({nodes:[{nodeCode:'SAME',name:'同域',domainId:'domain-1'},{nodeCode:'CROSS',name:'异域',domainId:'domain-2'},{nodeCode:'UNKNOWN',name:'未知域',domainId:''}]});
export const listSelfNodeKeys=async()=>({keys:[]});
export const getPoolSummary=async()=>({items:[]});
export const listSelfDistributionBatches=async()=>({items:[]});
export const consumePoolItem=async()=>{throw Error('测试禁止分发')};
export const signPoolEnvelope=consumePoolItem,requestNodeAuthorizations=consumePoolItem;
export const NODE_SELF_ERR={};
export const initializeSelfNode=consumePoolItem,renewSelfNodeKeygenAuthorization=consumePoolItem,listSelfNodeKeygenIssuances=async()=>({items:[]});
export const registerSelfNodePublicKey=consumePoolItem,initSelfNodeKeys=consumePoolItem,acquireDemoInitLease=consumePoolItem,releaseDemoInitLease=consumePoolItem,issueSelfNodeKeygen=consumePoolItem;
`
for (const match of readFileSync('src/api/pqkds/node-self.js','utf8').matchAll(/^export (?:async )?function (\w+)/gm)) {
 if (!nodeFixture.includes(match[1]+'=')) nodeFixture+=`\nexport const ${match[1]}=async()=>{throw Error('测试禁止调用 ${match[1]}')};`
}
let server, browser, socket, seq=0
const pending=new Map(),errors=[]
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))
function rpc(method,params={}) {return new Promise((resolve,reject)=>{
 const id=++seq,timer=setTimeout(()=>reject(Error(method)),15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))
})}
async function evaluate(expression) {const result=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result?.value}
async function waitFor(expression) {for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(100)}throw Error(expression+' '+errors.join(';'))}
try {
 server=await createServer({server:{port:5195,strictPort:true,fs:{allow:[join(process.cwd(),'../..')]}},plugins:[{
 name:'isolated-workbench',enforce:'pre',
 resolveId(id){if(/\/api\/nodes\/(nodes|domains)(\.js)?$/.test(id))return '\0domain-fixture';if(/\/api\/pqkds\/node-self(\.js)?$/.test(id))return '\0node-fixture'},
 load(id){if(id==='\0domain-fixture')return fixture;if(id==='\0node-fixture')return nodeFixture},
 configureServer(instance){instance.middlewares.use('/domain-fixture',async(_req,res)=>{
 const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="app"></div><script type="module">
 import {createApp,h} from 'vue';import ElementPlus from 'element-plus';import 'element-plus/dist/index.css';import '/src/assets/styles/index.scss';
 import {createRouter,createMemoryHistory} from 'vue-router';import Workbench from '/src/views/domains/index.vue';import SvgIcon from '/src/components/SvgIcon/index.vue';import 'virtual:svg-icons-register';
 import Distribute from '/src/views/distribute/index.vue';
 window.__mode='normal';window.__requests=[];const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:Workbench}]});await router.push('/');await router.isReady();
 createApp({render:()=>h('div',[h(SvgIcon,{iconClass:'database'}),h(location.search.includes('distribute')?Distribute:Workbench)])}).use(router).use(ElementPlus).mount('#app');</script></body></html>`;
 res.setHeader('Content-Type','text/html');res.end(await instance.transformIndexHtml('/domain-fixture',html));
 })}
 }]});await server.listen()
 browser=spawn(chrome,['--headless=new','--remote-debugging-port=9416',`--user-data-dir=${mkdtempSync(join(tmpdir(),'kms-domain-'))}`,'--no-first-run','about:blank'],{stdio:'ignore',windowsHide:true})
 let target;for(let i=0;i<60;i++){try{target=(await(await fetch('http://127.0.0.1:9416/json')).json()).find(row=>row.type==='page');if(target)break}catch{}await delay(200)}assert(target)
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
 socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
 const request=pending.get(message.id);if(!request)return;pending.delete(message.id);clearTimeout(request.timer);message.error?request.reject(Error(JSON.stringify(message.error))):request.resolve(message.result)})
 await rpc('Runtime.enable');await rpc('Page.enable');await rpc('Page.navigate',{url:'http://127.0.0.1:5195/domain-fixture'})

 await waitFor(`document.querySelectorAll('.domain-editor').length===2`)
 assert(await evaluate(`Boolean(document.querySelector('#icon-database'))`))
 await evaluate(`(()=>{const inputs=document.querySelectorAll('.create-domain input');['domain-3','空域','保留空域'].forEach((v,i)=>{inputs[i].value=v;inputs[i].dispatchEvent(new Event('input',{bubbles:true}))})})()`)
 await evaluate(`document.querySelector('.create-domain button').click()`)
 await waitFor(`window.__created?.domain_id==='domain-3'&&document.body.innerText.includes('空域')`)
 assert(await evaluate(`[...document.querySelectorAll('.el-table__row')].some(row=>row.innerText.includes('domain-3')&&row.innerText.includes('0'))`))
 for(const width of [1500,390]){
  await rpc('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});await delay(300)
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`))
  const screenshot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync(`.domain-${width}.png`,Buffer.from(screenshot.data,'base64'))
 }
 await evaluate(`document.querySelector('.domain-editor .el-select').click()`)
 await waitFor(`document.querySelectorAll('.el-select-dropdown__item').length>0`)
 await evaluate(`[...document.querySelectorAll('.el-select-dropdown__item')].find(e=>e.innerText==='domain-2').click()`)
 await evaluate(`document.querySelector('.domain-editor button').click()`)
 await waitFor(`window.__requests.length===1&&!document.querySelector('.el-loading-mask')`)
 assert.deepEqual(await evaluate(`window.__requests[0]`),{id:1,payload:{domain_id:'domain-2'}})
 assert(await evaluate(`document.querySelectorAll('.domain-editor').length===2`))
 await evaluate(`window.__mode='error';document.querySelector('.panel-head button').click()`)
 await waitFor(`document.body.innerText.includes('隔离接口失败')`)
 assert.equal(await evaluate(`document.querySelectorAll('.domain-editor').length`),0)
 await rpc('Page.navigate',{url:'http://127.0.0.1:5195/domain-fixture?distribute'})
 await waitFor(`document.body.innerText.includes('本节点所属域：domain-1')`)
 await evaluate(`[...document.querySelectorAll('.el-radio-button')].find(e=>e.innerText==='仅跨域').click()`)
 await evaluate(`document.querySelector('.el-form .el-select').click()`)
 await waitFor(`document.querySelectorAll('.el-select-dropdown__item').length===1`)
 assert(await evaluate(`document.querySelector('.el-select-dropdown__item').innerText.includes('CROSS')`))
 const screenshot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync('.domain-cross-390.png',Buffer.from(screenshot.data,'base64'))

 assert.equal(errors.length,0,errors.join(';'))
 console.log('PASS: 新增空域、节点改域、桌面/手机、请求失败、跨域筛选排除同域及未知域；隔离API，无真实业务写入')
} finally {socket?.close();browser?.kill();await server?.close()}
