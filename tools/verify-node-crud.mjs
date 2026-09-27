/**
 * 「节点管理」页的**界面级**增删验证（CDP 真浏览器）。
 *
 * 为什么不能只看渲染：页面能显示列表，不等于"我能管理它"。
 * 判据必须是：在界面上点出来的操作，真的落到了数据里，而且列表跟着变。
 * 所以这个脚本走完整交互链路：新增 → 断言出现在列表 → 删除 → 断言消失。
 *
 * 用法: node tools/verify-node-crud.mjs [--port 9222] [--keep]
 *   --keep  不删除测试节点（默认删掉，避免在演示环境里留垃圾）
 */
import { login } from './lib/captcha.mjs'
import { writeFileSync } from 'node:fs'

const argv = process.argv.slice(2)
const arg = (n, d) => {
  const i = argv.indexOf(`--${n}`)
  return i >= 0 ? argv[i + 1] : d
}
const PORT = arg('port', '9222')
const KEEP = argv.includes('--keep')
const ORIGIN = arg('origin', 'http://127.0.0.1')
const STAMP = Date.now().toString().slice(-6)
const NODE_ID = arg('node-id', `DEMO-PROBE-${STAMP}`)
const NODE_NAME = arg('node-name', `界面验证节点${STAMP}`)
const NODE_IP = arg('node-ip', `127.0.0.${100 + Number(STAMP.slice(-2))}`)
const NODE_PORT = arg('node-port', String(9100 + Number(STAMP.slice(-2))))

const base = `http://127.0.0.1:${PORT}`
const list = await (await fetch(`${base}/json/list`)).json()
let target = list.find((t) => t.type === 'page')
if (!target) target = await (await fetch(`${base}/json/new?about:blank`)).json()

const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id)
    pending.delete(msg.id)
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
  }
})
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const myId = ++id
    pending.set(myId, { resolve, reject })
    ws.send(JSON.stringify({ id: myId, method, params }))
  })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const evalJs = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error('JS 异常: ' + (r.exceptionDetails.exception?.description || ''))
  return r.result.value
}

const report = { nodeId: NODE_ID, steps: [] }
const step = (name, ok, detail) => {
  report.steps.push({ name, ok, detail })
  console.log(`${ok ? '  ✓' : '  ✗'} ${name}${detail ? '  — ' + detail : ''}`)
}

await new Promise((res) => ws.addEventListener('open', res, { once: true }))
await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })

// ---------------------------------------------------------------- 登录 + 进页面
//
// 与 verify-node-page.mjs 同理：**不用**填页面表单（登录页自己取的那张验证码，
// 其 uuid 在它的表单状态里，脚本读不到），改为宿主机取码登录后注入 Cookie。
const token = await login(ORIGIN, '/lifecycle-api', arg('user', 'admin'), arg('pass', 'admin123'))
await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
await sleep(2500)
await evalJs(`document.cookie = 'Admin-Token=${token}; path=/'`)
await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
await sleep(7000)
// ⚠️ 选择器必须**精确匹配叶子的 .menu-title**，不能对 li / .el-sub-menu__title 用
// `textContent.includes('节点管理')`：父级「分发与区块链」的子菜单 li 的 textContent
// 包含全部子项文本，会先命中它，点下去只是折叠/展开菜单，然后停在 /updatedel/index。
// （本脚本曾因此长期报"进入节点管理页"成功 —— 因为下面那步无条件传 true。）
await evalJs(`(() => {
  const title = [...document.querySelectorAll('.sidebar-container .menu-title')]
    .find(el => el.textContent.trim() === '节点管理');
  if (!title) return false;
  (title.closest('a') || title.closest('li') || title).click();
  return true;
})()`)
await sleep(5000)
// 如实断言：必须真的落在节点管理路由上，而不是无脑报成功
const nodePageHref = await evalJs('location.href')
step('进入「节点管理」页', /\/distchain\/nodes/.test(nodePageHref), nodePageHref)

// ---------------------------------------------------------------- 新增
await evalJs(`(() => {
  [...document.querySelectorAll('button')].find(b => b.textContent.includes('新增演示节点'))?.click();
  return true;
})()`)
await sleep(1500)

const filled = await evalJs(`(() => {
  const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null);
  if (!dlg) return { ok: false, why: '弹窗没出现' };
  const inputs = [...dlg.querySelectorAll('input')].filter(i => i.type !== 'checkbox');
  const setVal = (el, v) => {
    const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    s.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.blur();
  };
  // 顺序即表单顺序：节点ID / 名称 / IP / 端口 / (类型是 select) / 组织 / 联系人 / 描述
  setVal(inputs[0], ${JSON.stringify(NODE_ID)});
  setVal(inputs[1], ${JSON.stringify(NODE_NAME)});
  setVal(inputs[2], ${JSON.stringify(NODE_IP)});
  setVal(inputs[3], ${JSON.stringify(NODE_PORT)});
  return { ok: true, count: inputs.length, values: inputs.slice(0, 4).map(i => i.value) };
})()`)
step('填写新增表单', filled.ok, JSON.stringify(filled))

await evalJs(`(() => {
  const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null);
  const btn = [...dlg.querySelectorAll('.el-dialog__footer button')].find(b => b.textContent.replace(/\\s/g, '') === '确定');
  btn?.click();
  return !!btn;
})()`)

// 新增会同步生成 Kyber + 国密 + **Falcon**（2026-09-26 起 Falcon 也自动生成），
// 实测约 18~22 秒。原来固定 sleep(15s) 已经不够，改成轮询等待，超时放宽到 60s。
let created = false
let text = ''
for (let i = 0; i < 60; i++) {
  text = await evalJs(`(() => (document.querySelector('.app-main')?.innerText || '').replace(/\\s+/g,' '))()`)
  if (text.includes(NODE_ID)) { created = true; break }
  await sleep(1000)
}
step('新增后列表出现该节点', created, created ? NODE_ID : '未在列表中看到（60s 超时）')

// 点一下「刷新」，确保看到的是服务端真实状态而不是本地乐观更新
await evalJs(`(() => { [...document.querySelectorAll('button')].find(b => /刷\\s*新/.test(b.textContent))?.click(); return true; })()`)
await sleep(4000)
text = await evalJs(`(() => (document.querySelector('.app-main')?.innerText || '').replace(/\\s+/g,' '))()`)
step('刷新后仍在列表（服务端确实落库）', text.includes(NODE_ID))

const shotAdd = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(arg('out', 'node-crud-after-create.png'), Buffer.from(shotAdd.data, 'base64'))

// ---------------------------------------------------------------- 删除
if (!KEEP) {
  const clicked = await evalJs(`(() => {
    const rows = [...document.querySelectorAll('.el-table__row')];
    const row = rows.find(r => r.innerText.includes(${JSON.stringify(NODE_ID)}));
    if (!row) return false;
    const btn = [...row.querySelectorAll('button')].find(b => b.textContent.trim() === '删除');
    btn?.click();
    return !!btn;
  })()`)
  step('点击该行「删除」', clicked)
  await sleep(1500)
  const confirmed = await evalJs(`(() => {
    const box = document.querySelector('.el-message-box');
    if (!box) return false;
    const btn = [...box.querySelectorAll('button')].find(b => b.textContent.replace(/\\s/g, '') === '删除');
    btn?.click();
    return !!btn;
  })()`)
  step('确认删除', confirmed)
  await sleep(6000)
  text = await evalJs(`(() => (document.querySelector('.app-main')?.innerText || '').replace(/\\s+/g,' '))()`)
  step('删除后该节点从列表消失', !text.includes(NODE_ID))
  report.finalText = text.slice(0, 400)
}

const failed = report.steps.filter((s) => !s.ok)
console.log(`\n结果: ${report.steps.length - failed.length}/${report.steps.length} 通过`)
writeFileSync(arg('report', 'node-crud-report.json'), JSON.stringify(report, null, 2))
ws.close()
process.exit(failed.length ? 1 : 0)