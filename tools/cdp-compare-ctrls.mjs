// 对比同一行内表单中 el-input 与 el-select 的实际宽度
// 用法: node tools/cdp-compare-ctrls.mjs <cdpPort> <url>
const [, , port, url] = process.argv
const base = `http://127.0.0.1:${port}`
const list = await (await fetch(`${base}/json/list`)).json()
const target = list.find((t) => t.type === 'page')
const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result) }
})
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { resolve: res, reject: rej }); ws.send(JSON.stringify({ id: i, method, params })) })
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Page.enable'); await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url })
await new Promise((r) => setTimeout(r, 10000))
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true })).result.value

const res = await evalJs(`(() => {
  const rows = [];
  document.querySelectorAll('.el-form--inline .el-form-item').forEach((fi) => {
    const label = fi.querySelector('.el-form-item__label')?.textContent.trim() || '(无标签)';
    const content = fi.querySelector('.el-form-item__content');
    const ctrl = content?.querySelector('.el-select, .el-input, .el-date-editor, .el-cascader');
    if (!ctrl) return;
    const kind = ctrl.className.includes('el-select') ? 'el-select'
               : ctrl.className.includes('el-input') ? 'el-input'
               : ctrl.className.includes('el-date-editor') ? 'el-date-editor'
               : ctrl.className.includes('el-cascader') ? 'el-cascader' : 'other';
    rows.push({
      label, kind,
      ctrlW: Math.round(ctrl.getBoundingClientRect().width),
      contentW: Math.round(content.getBoundingClientRect().width),
      itemW: Math.round(fi.getBoundingClientRect().width),
      inlineStyle: ctrl.getAttribute('style') || ''
    });
  });
  return rows.slice(0, 40);
})()`)

console.log('行内表单控件宽度（前 40 项）：\n')
console.log('  控件类型          宽度   内容区  表单项  标签')
for (const r of res) {
  console.log(`  ${r.kind.padEnd(16)} ${String(r.ctrlW).padStart(5)}  ${String(r.contentW).padStart(6)}  ${String(r.itemW).padStart(6)}  ${r.label}${r.inlineStyle ? '  [' + r.inlineStyle + ']' : ''}`)
}
const collapsed = res.filter((r) => r.ctrlW <= 60)
console.log(`\n合计 ${res.length} 个控件，其中宽度 <= 60px（塌缩）: ${collapsed.length} 个`)
ws.close(); process.exit(0)
