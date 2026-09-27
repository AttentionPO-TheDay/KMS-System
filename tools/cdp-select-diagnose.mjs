// 诊断「分发类型」下拉：检查占位符、选中值渲染、弹层
// 用法: node tools/cdp-select-diagnose.mjs <cdpPort> <url> <outPrefix>
import { writeFileSync } from 'node:fs'

const [, , port, url, outPrefix] = process.argv
const base = `http://127.0.0.1:${port}`

const list = await (await fetch(`${base}/json/list`)).json()
const target = list.find((t) => t.type === 'page')
const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id)
    pending.delete(m.id)
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
  }
})
const send = (method, params = {}) =>
  new Promise((res, rej) => { const i = ++id; pending.set(i, { resolve: res, reject: rej }); ws.send(JSON.stringify({ id: i, method, params })) })

await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Page.enable'); await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url })
await new Promise((r) => setTimeout(r, 10000))

const evalJs = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value

// 1) 定位「分发类型」下拉，报告初始状态
const before = await evalJs(`(() => {
  const items = [...document.querySelectorAll('.el-form-item')];
  const fi = items.find(i => i.textContent.includes('分发类型'));
  if (!fi) return { found: false, labels: items.map(i => i.querySelector('.el-form-item__label')?.textContent.trim()).filter(Boolean) };
  const el = fi.querySelector('.el-select');
  const ph = el.querySelector('.el-select__placeholder');
  const input = el.querySelector('input');
  return {
    found: true,
    selectClass: el.className,
    placeholderHTML: ph ? ph.outerHTML.slice(0, 300) : null,
    placeholderText: ph ? ph.textContent : null,
    placeholderDisplay: ph ? getComputedStyle(ph).display : null,
    placeholderVisibility: ph ? getComputedStyle(ph).visibility : null,
    placeholderOpacity: ph ? getComputedStyle(ph).opacity : null,
    placeholderW: ph ? ph.getBoundingClientRect().width : null,
    inputValue: input ? input.value : null,
    inputW: input ? input.getBoundingClientRect().width : null,
    selectW: el.getBoundingClientRect().width
  };
})()`)
console.log('【点击前】', JSON.stringify(before, null, 1))

let shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
writeFileSync(`${outPrefix}-before.png`, Buffer.from(shot.data, 'base64'))

// 2) 点击打开下拉
await evalJs(`(() => {
  const items = [...document.querySelectorAll('.el-form-item')];
  const fi = items.find(i => i.textContent.includes('分发类型'));
  fi.querySelector('.el-select__wrapper').click();
  return true;
})()`)
await new Promise((r) => setTimeout(r, 1500))

const opened = await evalJs(`(() => {
  const dd = document.querySelector('.el-select-dropdown');
  const opts = [...document.querySelectorAll('.el-select-dropdown__item')];
  return {
    dropdownExists: !!dd,
    dropdownVisible: dd ? (dd.offsetWidth > 0 && dd.offsetHeight > 0) : false,
    dropdownDisplay: dd ? getComputedStyle(dd).display : null,
    dropdownVisibility: dd ? getComputedStyle(dd).visibility : null,
    dropdownOpacity: dd ? getComputedStyle(dd).opacity : null,
    dropdownRect: dd ? JSON.stringify(dd.getBoundingClientRect()) : null,
    dropdownZIndex: dd ? getComputedStyle(dd).zIndex : null,
    optionCount: opts.length,
    optionTexts: opts.map(o => o.textContent.trim()),
    optionHeights: opts.map(o => o.getBoundingClientRect().height)
  };
})()`)
console.log('【点开后】', JSON.stringify(opened, null, 1))

shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
writeFileSync(`${outPrefix}-open.png`, Buffer.from(shot.data, 'base64'))

// 3) 选中第一项
await evalJs(`(() => {
  const opts = [...document.querySelectorAll('.el-select-dropdown__item')];
  if (opts[0]) opts[0].click();
  return true;
})()`)
await new Promise((r) => setTimeout(r, 1500))

const after = await evalJs(`(() => {
  const items = [...document.querySelectorAll('.el-form-item')];
  const fi = items.find(i => i.textContent.includes('分发类型'));
  const el = fi.querySelector('.el-select');
  const ph = el.querySelector('.el-select__placeholder');
  const sel = el.querySelector('.el-select__selected-item:not(.el-select__placeholder)');
  return {
    selectText: el.textContent.trim(),
    placeholderHTML: ph ? ph.outerHTML.slice(0, 300) : null,
    selectedItemHTML: sel ? sel.outerHTML.slice(0, 300) : null,
    allSelectedItems: [...el.querySelectorAll('.el-select__selected-item')].map(n => ({
      cls: n.className, text: n.textContent.trim(),
      display: getComputedStyle(n).display,
      opacity: getComputedStyle(n).opacity,
      w: n.getBoundingClientRect().width
    }))
  };
})()`)
console.log('【选中后】', JSON.stringify(after, null, 1))

shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
writeFileSync(`${outPrefix}-after.png`, Buffer.from(shot.data, 'base64'))

ws.close(); process.exit(0)
