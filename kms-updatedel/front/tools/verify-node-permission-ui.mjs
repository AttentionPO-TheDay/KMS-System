// Actual node-management page and API payloads; isolated HTTP fixture, no production writes.
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const source = readFileSync('src/views/distribute/index.vue', 'utf8')
const describeError = new Function('error', source.match(/function describeError\(error\) \{([\s\S]*?)\r?\n\}\r?\n/)[1])
const denied = describeError({ errorCode: 'NODE_CAPABILITY_REQUIRED', message: '当前等级 L1' })
assert(denied.includes('当前等级 L1') && denied.includes('节点管理 → 编辑 → 权限等级'))
assert(!denied.includes('发起申请'))
assert(describeError({ errorCode: 'NOT_AUTHORIZED', message: '账号未关联节点' }).includes('账号未关联节点'))

const fixture = `
const rows=[{id:5,node_id:'A',name:'Node A',ip_address:'127.0.0.1',port:9001,
 permission_level:'L1',domain_id:'domain-1',node_type:'full',status:'active',falcon_key_ready:true}];
window.fixtureCalls=[];
export const unwrap=res=>res.data;
export const unwrapList=res=>res.data;
export default {
 async get(url){
  if(url==='/nodes/')return {data:structuredClone(rows)};
  if(url==='/domains/')return {data:[{domain_id:'domain-1'}]};
  throw Error('Unexpected GET '+url);
 },
 async post(url,data){
  if(url!=='/nodes/register/')throw Error('Unexpected POST '+url);
  window.fixtureCalls.push({method:'POST',url,data:structuredClone(data)});
  rows.push({...structuredClone(data),id:7,falcon_key_ready:true});
  return {data:{node_id:data.node_id,activation_code:'isolated-test-activation'}};
 },
 async patch(url,data){
  window.fixtureCalls.push({method:'PATCH',url,data:structuredClone(data)});
  if(window.failSave)throw Error('隔离测试：保存失败');
  const row=rows.find(row=>url==='/nodes/'+row.id+'/');
  if(!row)throw Error('Unexpected PATCH '+url);
  Object.assign(row,structuredClone(data));return {data:structuredClone(row)};
 }
};`
let vite, browser, socket, seq = 0
const pending = new Map(), errors = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => reject(Error(method)), 20000)
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result?.value
}
async function waitFor(expression) {
  for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await delay(100) }
  throw Error(expression + ': ' + errors.join(';'))
}
const dialog = `[...document.querySelectorAll('.el-dialog')].find(d=>d.offsetHeight>0)`
async function clickButton(label, scope = 'document') {
  await evaluate(`[...${scope}.querySelectorAll('button')].find(b=>b.textContent.replace(/\\s/g,'')===${JSON.stringify(label)}).click()`)
  await delay(300)
}
async function chooseLevel(level) {
  const field = `[...${dialog}.querySelectorAll('.el-form-item')].find(e=>e.textContent.includes('权限等级'))`
  await evaluate(`${field}.querySelector('.el-select').click()`)
  await delay(350)
  const option = `[...document.querySelectorAll('.el-select-dropdown__item')].find(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&e.textContent.startsWith('${level}（'))`
  await waitFor(option); await evaluate(`${option}.click()`)
  await waitFor(`${field}.textContent.includes('${level}（')`)
}
try {
  vite = await createServer({ server: { port: 5208, strictPort: true, fs: { allow: [join(process.cwd(), '../..')] } }, plugins: [{
    name: 'node-permission-isolated-http', enforce: 'pre',
    resolveId(id) { if (/\/api\/pqkds\/http(\.js)?$/.test(id)) return '\0node-permission-http' },
    load(id) { if (id === '\0node-permission-http') return fixture },
    configureServer(server) {
      server.middlewares.use('/node-permission-fixture', async (_req, res) => {
        const html = `<!doctype html><html lang="zh-CN"><body><div id="app"></div><script type="module">
        import {createApp,h} from 'vue';import ElementPlus from 'element-plus';
        import 'element-plus/dist/index.css';import '/src/assets/styles/index.scss';
        import Nodes from '/src/views/nodes/index.vue';
        createApp({render:()=>h(Nodes)}).use(ElementPlus).mount('#app');
        window.fixtureReady=true;</script></body></html>`
        res.setHeader('Content-Type', 'text/html'); res.end(await server.transformIndexHtml('/node-permission-fixture', html))
      })
    }
  }] }); await vite.listen()
  browser = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=9433',
    `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-node-permission-'))}`, '--no-first-run', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i = 0; i < 60; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9433/json')).json()).find(item => item.type === 'page'); if (target) break } catch {}
    await delay(150)
  }
  assert(target); socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
    const item = pending.get(message.id); if (!item) return
    pending.delete(message.id); clearTimeout(item.timer)
    message.error ? item.reject(Error(JSON.stringify(message.error))) : item.resolve(message.result)
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false })
  await rpc('Page.navigate', { url: 'http://127.0.0.1:5208/node-permission-fixture' })
  await waitFor(`window.fixtureReady&&document.querySelector('.el-table__body').textContent.includes('L1（仅查询）')`)
  await clickButton('编辑')
  await waitFor(`${dialog}?.textContent.includes('L1（仅查询）')`)
  await chooseLevel('L2'); await clickButton('保存', dialog)
  await waitFor(`document.querySelector('.el-table__body').textContent.includes('L2（查询、生成、分发）')`)
  assert.deepEqual(await evaluate('window.fixtureCalls[0]'), {
    method: 'PATCH', url: '/nodes/5/', data: { permission_level: 'L2', organization: '', domain_id: 'domain-1',
      department: '', contact_person: '', phone: '', email: '', location: '', node_type: 'full', tags: '', description: '' }
  })
  await clickButton('编辑'); await chooseLevel('L3')
  await evaluate('window.failSave=true'); await clickButton('保存', dialog)
  await waitFor(`${dialog}?.textContent.includes('隔离测试：保存失败')`)
  assert.equal(await evaluate(`document.querySelector('.el-table__body').textContent.includes('L2（查询、生成、分发）')`), true)
  await evaluate('window.failSave=false'); await clickButton('保存', dialog)
  await waitFor(`document.querySelector('.el-table__body').textContent.includes('L3（查询、生成、分发、更新、回收）')`)
  await clickButton('新增演示节点')
  await waitFor(`${dialog}?.textContent.includes('L1（仅查询）')`)
  await evaluate(`(()=>{const inputs=${dialog}.querySelectorAll('input');
    for(const [index,value] of [[0,'UI-C'],[1,'Node C'],[2,'127.0.0.3']]){
      inputs[index].value=value;inputs[index].dispatchEvent(new Event('input',{bubbles:true}));
    }})()`)
  await chooseLevel('L3'); await clickButton('确定', dialog)
  await waitFor(`window.fixtureCalls.some(c=>c.method==='POST')`)
  assert.equal(await evaluate(`window.fixtureCalls.find(c=>c.method==='POST').data.permission_level`), 'L3')
  await waitFor(`!${dialog}`)
  await clickButton('新增演示节点')
  await waitFor(`${dialog}?.textContent.includes('L1（仅查询）')`)
  await clickButton('取消', dialog)
  await clickButton('编辑')
  await waitFor(`${dialog}?.textContent.includes('L3（查询、生成、分发、更新、回收）')`)
  await evaluate('document.fonts.ready'); await delay(300)
  mkdirSync('../../tmp/node-permission', { recursive: true })
  const shot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync('../../tmp/node-permission/edit-level.png', Buffer.from(shot.data, 'base64'))
  assert.equal(errors.length, 0, errors.join(';'))
  console.log('PASS: actual node page; level column; edit L1→L2→L3; failed save retained; create payload; default reset; specific permission error')
} finally {
  socket?.close(); browser?.kill(); await vite?.close()
  for (const item of pending.values()) clearTimeout(item.timer)
}
