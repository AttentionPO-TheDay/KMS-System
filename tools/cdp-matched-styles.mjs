// 用 CDP CSS 域精确取得 .el-select 的命中规则（含被覆盖的）
// 用法: node tools/cdp-matched-styles.mjs <cdpPort> <url> <labelText>
const [, , port, url, labelText] = process.argv
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
await send('Page.enable'); await send('DOM.enable'); await send('CSS.enable'); await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url })
await new Promise((r) => setTimeout(r, 10000))

// 找到目标 select 的 DOM 节点
const { root } = await send('DOM.getDocument', { depth: -1, pierce: true })
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true })).result.value
const objectId = await evalJs(`(() => {
  const items = [...document.querySelectorAll('.el-form-item')];
  const fi = items.find(i => i.textContent.includes(${JSON.stringify(labelText)}));
  return fi ? (fi.querySelector('.el-select'), 1) : 0;
})()`).then(async () => {
  const r = await send('Runtime.evaluate', {
    expression: `(() => {
      const items = [...document.querySelectorAll('.el-form-item')];
      const fi = items.find(i => i.textContent.includes(${JSON.stringify(labelText)}));
      return fi ? fi.querySelector('.el-select') : null;
    })()`
  })
  return r.result.objectId
})

if (!objectId) { console.log('未找到目标 select'); process.exit(1) }
const { nodeId } = await send('DOM.requestNode', { objectId })

const matched = await send('CSS.getMatchedStylesForNode', { nodeId })
console.log('=== 命中 .el-select 的规则（含被覆盖）===')
for (const m of matched.matchedCSSRules || []) {
  const sel = m.rule.selectorList.text
  const props = m.rule.style.cssProperties.filter((p) => p.name === 'width' || p.name === 'min-width' || p.name === 'max-width' || p.name === 'flex' || p.name === 'display')
  if (!props.length) continue
  const origin = m.rule.origin
  console.log(`  [${origin}] ${sel}`)
  for (const p of props) {
    console.log(`      ${p.name}: ${p.value}${p.disabled ? '  (被覆盖)' : ''}${p.implicit ? '  (隐式)' : ''}`)
  }
}

console.log('\n=== 内联样式 ===')
console.log(' ', JSON.stringify(matched.inlineStyle?.cssProperties?.filter(p => /width|flex/.test(p.name)) || []))

console.log('\n=== 继承/祖先传递来的 width ===')
for (const m of matched.inherited || []) {
  const props = m.inlineStyle?.cssProperties?.filter((p) => p.name === 'width')
  if (props?.length) console.log('  inherited:', JSON.stringify(props))
}
ws.close(); process.exit(0)
