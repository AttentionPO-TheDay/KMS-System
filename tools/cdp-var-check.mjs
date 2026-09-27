// 检查目标元素上 CSS 自定义属性的实际解析结果
// 用法: node tools/cdp-var-check.mjs <cdpPort> <url> <labelText>
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
  const el = fi.querySelector('.el-select');
  const cs = getComputedStyle(el);

  const probe = (node) => ({
    tag: node.tagName.toLowerCase(),
    cls: (node.className||'').toString().slice(0,60),
    selectWidth: getComputedStyle(node).getPropertyValue('--el-select-width'),
    width: getComputedStyle(node).width,
    display: getComputedStyle(node).display,
    rectW: Math.round(node.getBoundingClientRect().width)
  });

  // 逐层向上找 --el-select-width 的来源
  const chain = [];
  let n = el;
  while (n && n !== document.documentElement.parentElement) {
    chain.push(probe(n));
    n = n.parentElement;
  }

  // 直接测试变量能否解析
  const testDiv = document.createElement('div');
  testDiv.style.width = 'var(--el-select-width)';
  document.body.appendChild(testDiv);
  const resolved = getComputedStyle(testDiv).width;
  testDiv.remove();

  return {
    onSelect: cs.getPropertyValue('--el-select-width'),
    selectWidth: cs.width,
    selectDisplay: cs.display,
    selectRectW: Math.round(el.getBoundingClientRect().width),
    contentRectW: Math.round(fi.querySelector('.el-form-item__content').getBoundingClientRect().width),
    varResolvesTo: resolved,
    chain: chain.slice(0, 5)
  };
})()`)

console.log('【目标 select】')
console.log('  --el-select-width =', JSON.stringify(res.onSelect))
console.log('  computed width    =', res.selectWidth)
console.log('  computed display  =', res.selectDisplay)
console.log('  rect width        =', res.selectRectW)
console.log('  父 content rect   =', res.contentRectW)
console.log('  临时div width:var(--el-select-width) 解析为 =', res.varResolvesTo)
console.log('\n【祖先链上该变量的取值】')
res.chain.forEach((c, i) => console.log(`  ${i}. <${c.tag} class="${c.cls}"> var=${JSON.stringify(c.selectWidth)} width=${c.width} display=${c.display} rectW=${c.rectW}`))
ws.close(); process.exit(0)
