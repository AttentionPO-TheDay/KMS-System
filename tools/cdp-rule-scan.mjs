// 找出把 .el-select 压到 44px 的规则：扫描所有含 el-select / el-form-item / query-form 的 CSS 规则
// 用法: node tools/cdp-rule-scan.mjs <cdpPort> <url>
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
await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url })
await new Promise((r) => setTimeout(r, 10000))
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true })).result.value

const res = await evalJs(`(() => {
  const hits = [];
  for (const sheet of document.styleSheets) {
    let rs; try { rs = sheet.cssRules } catch { continue }
    const walk = (list) => {
      for (const rule of list) {
        if (rule.cssRules) { walk(rule.cssRules); continue }
        if (!rule.selectorText || !rule.style) continue;
        const sel = rule.selectorText;
        if (!/el-select|el-form-item|query-form/i.test(sel)) continue;
        const css = rule.style.cssText;
        hits.push({ sel: sel.slice(0, 160), css: css.slice(0, 240) });
      }
    }
    walk(rs)
  }
  return hits;
})()`)

console.log(`共 ${res.length} 条相关规则：\n`)
for (const h of res) console.log(`  ${h.sel}\n      { ${h.css} }\n`)
ws.close(); process.exit(0)
