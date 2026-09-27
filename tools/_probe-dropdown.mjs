import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'
const ORIGIN='http://127.0.0.1', CDP_PORT=9233
const CHROME=['C:/Program Files/Google/Chrome/Application/chrome.exe'].find(existsSync)
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms))
const dir=mkdtempSync(join(tmpdir(),'dd-'))
const chrome=spawn(CHROME,[`--remote-debugging-port=${CDP_PORT}`,`--user-data-dir=${dir}`,'--headless=new','--no-first-run','--window-size=1680,1000','about:blank'],{stdio:'ignore'})
let ws,id=0
const rpc=(m,p={})=>new Promise((res,rej)=>{const n=++id
 const on=(e)=>{const x=JSON.parse(typeof e.data==='string'?e.data:e.data.toString())
  if(x.id===n){ws.removeEventListener('message',on);x.error?rej(new Error(JSON.stringify(x.error))):res(x.result)}}
 ws.addEventListener('message',on);ws.send(JSON.stringify({id:n,method:m,params:p}))})
const ev=async(e)=>(await rpc('Runtime.evaluate',{expression:e,awaitPromise:true,returnByValue:true})).result?.value
try{
 let t=null
 for(let i=0;i<40&&!t;i++){try{t=(await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find(x=>x.type==='page')}catch{};if(!t)await sleep(500)}
 ws=new WebSocket(t.webSocketDebuggerUrl)
 await new Promise(r=>ws.addEventListener('open',r,{once:true}))
 await rpc('Runtime.enable');await rpc('Page.enable')
 const token=await login(ORIGIN,'/updatedel-api','admin','admin123')
 await rpc('Page.navigate',{url:`${ORIGIN}/user/`});await sleep(2500)
 await ev(`document.cookie='Admin-Token=${token}; path=/'`)
 await rpc('Page.navigate',{url:`${ORIGIN}/updatedel/distchain/keypool`});await sleep(9000)
 await ev(`[...document.querySelectorAll('button')].find(x=>x.innerText.includes('生成并分发'))?.click()`)
 await sleep(1800)
 const r = await ev(`(()=>{const s=[...[...document.querySelectorAll('.el-dialog')].find(d=>d.innerText.includes('生成并分发')).querySelectorAll('.el-select')][1];const i=s.querySelector('input');const b=i.getBoundingClientRect();return {x:Math.round(b.left+b.width/2),y:Math.round(b.top+b.height/2)}})()`)
 console.log('sender select input rect:', JSON.stringify(r))
 await rpc('Input.dispatchMouseEvent',{type:'mousePressed',x:r.x,y:r.y,button:'left',clickCount:1,buttons:1})
 await rpc('Input.dispatchMouseEvent',{type:'mouseReleased',x:r.x,y:r.y,button:'left',clickCount:1,buttons:1})
 await sleep(1500)
 console.log(JSON.stringify(await ev(`(()=>{
   const poppers=[...document.querySelectorAll('[class*=dropdown],[class*=popper]')]
   return poppers.map(p=>{const b=p.getBoundingClientRect();return {cls:(p.className||'').toString().slice(0,60), w:Math.round(b.width), h:Math.round(b.height),
     itemCls:[...p.querySelectorAll('*')].map(e=>(e.className||'').toString()).filter(c=>/item/.test(c)).slice(0,3)}}).filter(x=>x.w>0||x.h>0)
 })()`),null,1))
}catch(e){console.error('probe failed:',e.message)}finally{try{ws?.close()}catch{};chrome.kill()}