// 检查 el-select 内部各层的宽度，定位塌缩点
// 用法: node tools/cdp-inner-width.mjs <cdpPort> <url> <labelText>
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
await send('Page.enable'); await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url })
await new Promise((r) => setTimeout(r, 10000))
const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true })).result.value

const res = await evalJs(`(() => {
  const items = [...document.querySelectorAll('.el-form-item')];
  const fi = items.find(i => i.textContent.includes(${JSON.stringify(labelText)}));
  const sel = fi.querySelector('.el-select');
  const dump = (el, label) => {
    if (!el) return { label, missing: true };
    const cs = getComputedStyle(el);
    return {
      label,
      cls: (el.className||'').toString().slice(0,80),
      rectW: Math.round(el.getBoundingClientRect().width),
      width: cs.width, minWidth: cs.minWidth, maxWidth: cs.maxWidth,
      display: cs.display, flex: cs.flex, position: cs.position,
      boxSizing: cs.boxSizing, overflow: cs.overflow,
      flexGrow: cs.flexGrow, flexShrink: cs.flexShrink, flexBasis: cs.flexBasis
    };
  };
  const wrapper = sel.querySelector('.el-select__wrapper');
  const selection = sel.querySelector('.el-select__selection');
  const suffix = sel.querySelector('.el-select__suffix');
  const ph = sel.querySelector('.el-select__placeholder');
  const inputWrap = sel.querySelector('.el-select__input-wrapper');
  const input = sel.querySelector('input');

  return {
    select: dump(sel, 'select'),
    formItem: dump(fi, 'form-item'),
    content: dump(fi.querySelector('.el-form-item__content'), 'content'),
    wrapper: dump(wrapper, 'wrapper'),
    selection: dump(selection, 'selection'),
    inputWrapper: dump(inputWrap, 'input-wrapper'),
    input: dump(input, 'input'),
    suffix: dump(suffix, 'suffix'),
    placeholder: dump(ph, 'placeholder'),
    // wrapper 的 inline style
    wrapperInline: wrapper ? wrapper.getAttribute('style') : null,
    selectInline: sel.getAttribute('style')
  };
})()`)

for (const [k, v] of Object.entries(res)) {
  if (k.endsWith('Inline')) { console.log(`${k}: ${JSON.stringify(v)}`); continue }
  if (v.missing) { console.log(`${k}: 不存在`); continue }
  console.log(`${k}:`)
  console.log(`   rectW=${v.rectW} width=${v.width} display=${v.display} flex=${v.flex} minWidth=${v.minWidth} overflow=${v.overflow}`)
  if (v.cls) console.log(`   class="${v.cls}"`)
}
ws.close(); process.exit(0)
