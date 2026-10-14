/** Read-only page fixture using real Demo APIs; never saves or rotates business keys. */
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const nodeId = process.argv[2] || 'demo-0'
const falconMode = process.env.KMS_UI_COMPONENT === 'falcon'
const distributionMode = process.env.KMS_UI_COMPONENT === 'distribution'
const entryMode = process.env.KMS_UI_COMPONENT === 'entry'
const pageModule = distributionMode ? '/src/views/distribute/index.vue'
  : falconMode ? '/src/components/FalconEncryptionSupplement/index.vue' : '/src/views/keyupdate/index.vue'
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
assert(chrome)
let browser, socket, server
const pending = new Map()
let sequence = 0
const errors = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function rpc(method, params = {}) {
  const id = ++sequence
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)) }, 15000)
    pending.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const reply = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (reply.exceptionDetails) throw new Error(JSON.stringify(reply.exceptionDetails))
  return reply.result?.value
}
try {
  server = await createServer({ server: { host: '127.0.0.1', port: 5187, strictPort: true,
    fs: { allow: [fileURLToPath(new URL('../../../', import.meta.url))] },
    proxy: { '/demo-api': { target: 'http://127.0.0.1:8088', changeOrigin: true } } },
    plugins: [{ name: 'read-only-auto-update-fixture', configureServer(instance) {
      instance.middlewares.use('/auto-update-fixture', async (_req, res) => {
        const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head><body><div id="app"></div><script type="module">
          import { createApp } from 'vue'; import ElementPlus from 'element-plus';
          import 'element-plus/dist/index.css';
          import Page from '${pageModule}';
          import { loadDemoContext } from '/src/utils/demo-context.js';
          try {
            let response = await fetch('/demo-api/lifecycle/demo/context'); let envelope = await response.json();
            const ctx = envelope.data; const headers = {'Content-Type':'application/json'};
            if(ctx?.csrfToken){headers['X-Kms-Demo-CSRF']=ctx.csrfToken;headers['X-Kms-Demo-Revision']=String(ctx.revision)}
            response = await fetch('/demo-api/lifecycle/demo/context/entry', {method:'POST',headers,body:JSON.stringify({nodeId:${JSON.stringify(nodeId)}})});
            envelope = await response.json(); if(envelope.code!==200)throw new Error(envelope.msg);
            await loadDemoContext(true);
            createApp(Page).use(ElementPlus).mount('#app'); window.__mounted=true;
          } catch(error){ window.__error=error.message }
        </script></body></html>`
        res.setHeader('Content-Type', 'text/html')
        res.end(await instance.transformIndexHtml('/auto-update-fixture', html))
      })
    } }] })
  await server.listen()
  browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=9398',
    `--user-data-dir=${mkdtempSync(join(tmpdir(), 'kms-auto-update-readonly-'))}`,
    '--no-first-run', '--window-size=1680,1100', 'about:blank'], { stdio: 'ignore', windowsHide: true })
  let target
  for (let i = 0; i < 60; i++) {
    try { target = (await (await fetch('http://127.0.0.1:9398/json')).json()).find(row => row.type === 'page'); if (target) break } catch {}
    await delay(200)
  }
  assert(target)
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
    const request = pending.get(message.id)
    if (!request) return
    pending.delete(message.id); clearTimeout(request.timer)
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result)
  })
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Page.navigate', { url: entryMode ? 'http://127.0.0.1:8088/updatedel/demo' : 'http://127.0.0.1:5187/auto-update-fixture' })
  if (entryMode) {
    await delay(3500)
    const state = await evaluate(`({text:document.body.innerText.slice(0,1200),disabled:document.querySelector('.entry-card input')?.disabled})`)
    console.log(JSON.stringify(state))
    assert.equal(state.disabled, false, 'deployed anonymous entry is usable')
    await evaluate(`fetch('/demo-api/lifecycle/demo/context/entry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nodeId:'__missing_entry_regression__'})}).then(r=>r.json())`)
    await rpc('Page.navigate', { url: 'http://127.0.0.1:8088/updatedel/demo' })
    await delay(2500)
    assert.equal(await evaluate(`document.querySelector('.entry-card input')?.disabled`), false,
      'persisted anonymous session after failed entry must not lock the page')
    await evaluate(`(()=>{const input=document.querySelector('.entry-card input');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'demo-0');
      input.dispatchEvent(new Event('input',{bubbles:true}));})()`)
    await delay(100)
    await evaluate(`[...document.querySelectorAll('.entry-card button')].find(b=>b.innerText.includes('进入节点')).click()`)
    await delay(3500)
    assert(await evaluate(`location.pathname.startsWith('/updatedel/demo/node/')`), 'valid node entry navigates into node area')
    assert.equal(errors.length, 0, errors.join('; '))
    console.log('PASS: 正式部署新会话与失败后匿名会话可输入、真实 demo-0 进入节点区域；未生成业务密钥')
  } else {
  let ready = false
  for (let i = 0; i < 120; i++) {
    const selector = distributionMode ? '.el-select__wrapper' : falconMode ? '.falcon-supplement button:not([disabled])' : '.key-update__header button:not([disabled])'
    const state = await evaluate(`({error:window.__error,ready:window.__mounted&&!!document.querySelector(${JSON.stringify(selector)})})`)
    assert(!state.error, state.error)
    if (state.ready) { ready = true; break }
    await delay(250)
  }
  assert(ready, 'live node page loads')
  if (distributionMode) {
    await delay(3500)
    await evaluate(`document.querySelector('.el-select__wrapper').click()`)
    await delay(300)
    const options = await evaluate(`[...document.querySelectorAll('.el-select-dropdown__item')].map(e=>e.innerText.trim())`)
    assert(await evaluate(`(()=>{const option=[...document.querySelectorAll('.el-select-dropdown__item')].find(e=>e.innerText.includes('demo-1'))||[...document.querySelectorAll('.el-select-dropdown__item')].find(e=>!e.classList.contains('is-disabled'));if(!option)return false;option.click();return true})()`), `recipient is selectable: ${JSON.stringify(options)}`)
    await delay(600)
    assert(await evaluate(`(()=>{const radio=document.querySelector('input[value="FALCON_CL_V1"]');if(!radio||radio.disabled)return false;radio.click();return true})()`), 'lattice encryption is selectable without sender encryption material')
    await delay(800)
    assert(await evaluate(`document.querySelector('input[value="FALCON_CL_V1"]').checked`))
    assert(await evaluate(`document.body.innerText.includes('改进型无证书格加密（实验版 v1）')`))
    assert(await evaluate(`document.body.innerText.includes('刷新接收方密钥')`))
    assert.equal(errors.length, 0, errors.join('; '))
    const screenshot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    writeFileSync('.distribution-algorithm-ui.png', Buffer.from(screenshot.data, 'base64'))
    console.log('PASS: 真实分发页面选择接收节点与格加密算法、新名称、刷新入口；未发送业务密钥')
  } else if (falconMode) {
    let available = false
    for (let i = 0; i < 60; i++) {
      available = await evaluate(`!![...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='补充格加密密钥'&&!b.disabled)`)
      if (available) break
      await delay(200)
    }
    assert(available, 'activated node can supplement independently of initialization')
    assert(await evaluate(`document.body.innerText.includes('现有签名密钥继续用于签名')`))
    assert.equal(errors.length, 0, errors.join('; '))
    const screenshot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    writeFileSync('.falcon-supplement-ui.png', Buffer.from(screenshot.data, 'base64'))
    console.log('PASS: 真实 ACTIVE 节点检查通过，补充按钮可操作；未生成/更换任何业务密钥')
  } else {
  assert(await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='自动更新设置');if(!b||b.disabled)return false;b.click();return true})()`))
  for (let i = 0; i < 60; i++) {
    if (await evaluate('document.querySelectorAll(".key-update__auto .el-switch").length===4')) break
    await delay(200)
  }
  const state = await evaluate(`({switches:document.querySelectorAll('.key-update__auto .el-switch').length,
    intervals:document.querySelectorAll('.key-update__auto input[role="spinbutton"]').length,
    text:document.querySelector('.key-update__auto')?.innerText,
    canSave:[...document.querySelectorAll('.key-update__auto button')].some(b=>b.innerText==='保存'&&!b.disabled)})`)
  assert.equal(state.switches, 4)
  assert.equal(state.intervals, 4)
  assert(state.text.includes('下次：'))
  assert(!state.text.includes('读取自动更新配置失败'), state.text)
  assert.equal(state.canSave, false, 'fresh profile without original secrets cannot enable rotation')
  await evaluate(`(()=>{const input=document.querySelector('.key-update__auto input[role="spinbutton"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'30');
    input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
    document.querySelector('.key-update__auto .el-select__wrapper').click()})()`)
  await delay(200)
  assert(await evaluate(`(()=>{const option=[...document.querySelectorAll('.el-select-dropdown__item')].find(e=>e.innerText.trim()==='分钟');if(!option)return false;option.click();return true})()`))
  await delay(200)
  const selection = await evaluate(`document.querySelector('.key-update__auto .el-select__wrapper').innerText.trim()`)
  assert.equal(selection, '分钟')
  assert.equal(await evaluate(`document.querySelector('.key-update__auto input[role="spinbutton"]').value`), '30')
  assert.equal(errors.length, 0, errors.join('; '))
  const screenshot = await rpc('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync('.auto-update-ui.png', Buffer.from(screenshot.data, 'base64'))
  console.log('PASS: 真实 API 页面载入、按钮展开、4 组间隔/开关、选择 30 分钟、状态展示、缺少本机材料时禁止启用；未写入业务配置')
  }
  }
} finally {
  socket?.close(); browser?.kill(); await server?.close()
  for (const request of pending.values()) clearTimeout(request.timer)
}
