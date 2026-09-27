// 通过 CDP 打开页面 → 点击「自动更新配置」页签 → 截取筛选区
// 用法: node tools/cdp-shot.mjs <cdpPort> <url> <tabText> <outFile>
import { writeFileSync } from 'node:fs'

const [, , port, url, tabText, outFile] = process.argv
const base = `http://127.0.0.1:${port}`

const list = await (await fetch(`${base}/json/list`)).json()
let target = list.find((t) => t.type === 'page')
if (!target) {
  target = await (await fetch(`${base}/json/new?about:blank`)).json()
}

const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
const events = []

ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id)
    pending.delete(msg.id)
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
  } else if (msg.method) {
    events.push(msg)
  }
})

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const myId = ++id
    pending.set(myId, { resolve, reject })
    ws.send(JSON.stringify({ id: myId, method, params }))
  })

await new Promise((res) => ws.addEventListener('open', res, { once: true }))

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: 1500, height: 950, deviceScaleFactor: 1, mobile: false
})

await send('Page.navigate', { url })
// 等待渲染完成
await new Promise((r) => setTimeout(r, 9000))

// 读取筛选区诊断信息
const probe = await send('Runtime.evaluate', {
  expression: `(() => {
    const out = { tabs: [], selects: [], buttons: [] };
    document.querySelectorAll('.inner-sidenav .nav-item').forEach(n =>
      out.tabs.push(n.textContent.trim()));
    // 点击目标页签
    let clicked = false;
    document.querySelectorAll('.inner-sidenav .nav-item').forEach(n => {
      if (!clicked && n.textContent.includes(${JSON.stringify(tabText)})) { n.click(); clicked = true; }
    });
    out.clicked = clicked;
    out.activeTab = document.querySelector('.inner-sidenav .nav-item.active')?.textContent.trim() || '';
    return out;
  })()`,
  returnByValue: true
})
console.log('页签:', JSON.stringify(probe.result.value, null, 1))

await new Promise((r) => setTimeout(r, 2500))

// 采集筛选区 select / 按钮的真实计算样式
const diag = await send('Runtime.evaluate', {
  expression: `(() => {
    const pane = [...document.querySelectorAll('.tab-pane')].find(p => p.offsetParent !== null || p.style.display !== 'none');
    const res = { paneFound: !!pane, selects: [], buttons: [] };
    const scope = pane || document;
    scope.querySelectorAll('.el-select').forEach((el, i) => {
      const ph = el.querySelector('.el-select__placeholder');
      const caret = el.querySelector('.el-select__caret');
      const cs = getComputedStyle(el);
      res.selects.push({
        i,
        visible: el.offsetWidth > 0 && el.offsetHeight > 0,
        w: el.offsetWidth, h: el.offsetHeight,
        display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
        disabledClass: el.className.includes('is-disabled'),
        placeholderText: ph ? ph.textContent.trim() : null,
        placeholderColor: ph ? getComputedStyle(ph).color : null,
        placeholderOpacity: ph ? getComputedStyle(ph).opacity : null,
        caretFound: !!caret,
        caretDisplay: caret ? getComputedStyle(caret).display : null,
        caretW: caret ? caret.getBoundingClientRect().width : null,
        caretH: caret ? caret.getBoundingClientRect().height : null
      });
    });
    scope.querySelectorAll('button.el-button').forEach((b, i) => {
      res.buttons.push({ i, text: b.textContent.trim(), disabled: b.disabled });
    });
    return res;
  })()`,
  returnByValue: true
})
console.log('筛选区诊断:', JSON.stringify(diag.result.value, null, 1))

const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
writeFileSync(outFile, Buffer.from(shot.data, 'base64'))
console.log('截图已保存:', outFile)

ws.close()
process.exit(0)
