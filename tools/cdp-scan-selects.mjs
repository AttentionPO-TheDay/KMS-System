// 全站扫描：统计所有 el-select 的宽度，找出仍塌缩的
// 用法: node tools/cdp-scan-selects.mjs <cdpPort> <url>
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
await new Promise((r) => setTimeout(r, 11000))
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true })).result.value

const res = await evalJs(`(() => {
  const out = [];
  document.querySelectorAll('.el-select').forEach((el) => {
    const w = Math.round(el.getBoundingClientRect().width);
    const ph = el.querySelector('.el-select__placeholder');
    // 找到所属 tab-pane 是否可见
    const pane = el.closest('.tab-pane');
    const paneVisible = pane ? (pane.style.display !== 'none') : true;
    if (!paneVisible) return;
    out.push({
      w,
      placeholder: ph ? ph.textContent.trim() : '',
      placeholderW: ph ? Math.round(ph.getBoundingClientRect().width) : 0,
      inlineStyle: el.getAttribute('style') || '',
      cls: el.className
    });
  });
  const collapsed = out.filter((o) => o.w > 0 && o.w <= 60);
  return { total: out.length, collapsed, all: out };
})()`)

console.log(`可见的 el-select 总数: ${res.total}`)
console.log(`\n仍塌缩（<=60px）: ${res.collapsed.length}`)
res.collapsed.forEach((o) => console.log(`  w=${o.w} placeholderW=${o.placeholderW} "${o.placeholder}" style="${o.inlineStyle}"`))
console.log('\n全部宽度分布:')
res.all.sort((a, b) => a.w - b.w).forEach((o) => console.log(`  w=${String(o.w).padStart(4)}  ph=${String(o.placeholderW).padStart(4)}  "${o.placeholder}"`))
ws.close(); process.exit(0)
