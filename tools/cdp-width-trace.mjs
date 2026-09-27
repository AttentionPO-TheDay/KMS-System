// 定位 el-select 宽度只有 44px 的原因：遍历匹配的 CSS 规则 + 逐层祖先宽度
// 用法: node tools/cdp-width-trace.mjs <cdpPort> <url>
import { writeFileSync } from 'node:fs'

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

const out = await evalJs(`(() => {
  const items = [...document.querySelectorAll('.el-form-item')];
  const fi = items.find(i => i.textContent.includes('分发类型'));
  const el = fi.querySelector('.el-select');

  // 逐层祖先的宽度信息
  const chain = [];
  let n = el;
  while (n && n !== document.documentElement) {
    const cs = getComputedStyle(n);
    chain.push({
      tag: n.tagName.toLowerCase(),
      cls: (n.className || '').toString().slice(0, 70),
      width: cs.width, display: cs.display, flex: cs.flex,
      minWidth: cs.minWidth, maxWidth: cs.maxWidth,
      rectW: Math.round(n.getBoundingClientRect().width)
    });
    n = n.parentElement;
  }

  // 遍历所有匹配 el-select 的规则，找出声明 width 的
  const rules = [];
  for (const sheet of document.styleSheets) {
    let list2;
    try { list2 = sheet.cssRules } catch { continue }
    const walk = (rs) => {
      for (const rule of rs) {
        if (rule.cssRules) { walk(rule.cssRules); continue }
        if (!rule.selectorText || !rule.style) continue;
        const decl = rule.style.getPropertyValue('width') || rule.style.getPropertyValue('min-width') || rule.style.getPropertyValue('flex');
        if (!decl) continue;
        const sel = rule.selectorText;
        if (!/select|form-item|inline|wrapper|input/i.test(sel)) continue;
        let matches = false;
        try { matches = el.matches(sel) } catch { matches = false }
        rules.push({ sel: sel.slice(0, 120), width: rule.style.getPropertyValue('width'), minWidth: rule.style.getPropertyValue('min-width'), flex: rule.style.getPropertyValue('flex'), matchesSelf: matches });
      }
    }
    walk(list2)
  }

  return { selectRectW: Math.round(el.getBoundingClientRect().width), chain, rules: rules.slice(0, 40) };
})()`)

console.log('select 实际宽度:', out.selectRectW)
console.log('\n=== 祖先链宽度（从 select 往上）===')
out.chain.forEach((c, i) => console.log(`  ${i}. <${c.tag} class="${c.cls}"> rectW=${c.rectW} width=${c.width} display=${c.display} flex=${c.flex} minW=${c.minWidth}`))
console.log('\n=== 声明了 width/min-width/flex 且与 select 相关的规则 ===')
out.rules.forEach((r) => {
  const parts = []
  if (r.width) parts.push(`width:${r.width}`)
  if (r.minWidth) parts.push(`min-width:${r.minWidth}`)
  if (r.flex) parts.push(`flex:${r.flex}`)
  console.log(`  ${r.matchesSelf ? '[命中select]' : '[未命中]'} ${parts.join(' ')}  ${r.sel}`)
})
ws.close(); process.exit(0)
