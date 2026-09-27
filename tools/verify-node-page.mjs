/**
 * 管理端「节点管理」页的真实浏览器验证（CDP，不依赖 puppeteer）。
 *
 * 为什么必须用真浏览器：这一页的故障史全是"HTTP 层面看着都对，页面上却什么都没有"——
 *   * 菜单查得到、接口返回 200；
 *   * 但内容是 iframe 内嵌的 /distribute/，而那个子应用有自己的登录态，
 *     未登录时渲染的是登录页 —— 从 curl 完全看不出来。
 * 所以判据只能是"渲染后的 DOM 里有什么"。
 *
 * 用法:
 *   node tools/verify-node-page.mjs [--port 9222] [--out shot.png] [--keep-open]
 *
 * 输出（JSON，便于脚本消费）：
 *   { loggedIn, menuClicked, frameSrc, frameText, contentText, shot }
 */
import { login } from './lib/captcha.mjs'
import { writeFileSync } from 'node:fs'

function arg(name, dflt) {
  const i = process.argv.indexOf(`--${name}`)
  return i >= 0 ? process.argv[i + 1] : dflt
}
const PORT = arg('port', '9222')
const OUT = arg('out', 'node-page.png')
const ORIGIN = arg('origin', 'http://127.0.0.1')
const USER = arg('user', 'admin')
const PASS = arg('pass', 'admin123')
const MENU = arg('menu', '节点管理')

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
  if (r.exceptionDetails) throw new Error('JS 异常: ' + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails))
  return r.result.value
}

await new Promise((res) => ws.addEventListener('open', res, { once: true }))
await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })

// ★ toast 收集器必须在**页面脚本之前**注入。
// Element Plus 的消息 3 秒自动消失，而"有没有弹红条"正是这一页曾经的故障现象；
// 事后再查 DOM 查不到，跨 CDP 调用存 window 变量也会被导航清掉。
// addScriptToEvaluateOnNewDocument 能把监听装在文档创建前，导航也不丢。
await send('Page.addScriptToEvaluateOnNewDocument', {
  source: `
    window.__toasts = [];
    (function () {
      const pick = (node) => {
        if (!node || node.nodeType !== 1) return;
        const hit = [];
        if (node.matches && node.matches('.el-message, .el-notification')) hit.push(node);
        if (node.querySelectorAll) node.querySelectorAll('.el-message, .el-notification').forEach((x) => hit.push(x));
        hit.forEach((x) =>
          window.__toasts.push(
            (x.className.includes('error') ? '[错误] ' : '[提示] ') + (x.innerText || '').replace(/\\s+/g, ' ').slice(0, 200)
          )
        );
      };
      const start = () => new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach(pick)))
        .observe(document.body, { childList: true, subtree: true });
      if (document.body) start();
      else document.addEventListener('DOMContentLoaded', start);
    })();
  `
})

const report = {
  loggedIn: false,
  loginError: null,
  menuClicked: false,
  menuError: null,
  frameSrc: null,
  frameText: null,
  contentText: null,
  toasts: [],
  shot: OUT
}

// ---------------------------------------------------------------- 登录
//
// ⚠️ 不要用"填页面表单 + 点登录"的方式（原来就是这么写的）：
// 登录页在挂载时会**自己**取一张验证码，uuid 存在它的表单状态里；
// 脚本读不到那个 uuid，只能拿自己取的答案去填 —— 服务端按页面提交的 uuid 校验，
// 必然失败。这不是验证码"挡住了脚本"，而是脚本用错了方式。
//
// 这里改成：在宿主机上取码登录拿到令牌，再把令牌写进 Cookie（与其它脚本一致）。
// 走的是**同一条服务端校验**，页面上也没有留任何后门。
try {
  const token = await login(ORIGIN, '/lifecycle-api', USER, PASS)
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
  await sleep(2500)
  await evalJs(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
  await sleep(6000)
  const url = await evalJs('location.href')
  report.loggedIn = !url.includes('/login')
  if (!report.loggedIn) report.loginError = '注入令牌后仍停留在 ' + url
} catch (e) {
  report.loginError = String(e.message)
}

// ------------------------------------------------------- 点击「节点管理」菜单
// 先把侧边栏展开：折叠态下 Element Plus **不渲染菜单文字**，
// 于是"按文字找菜单项"必然找不到 —— 而报出来的错会是"侧边栏里没找到菜单项"，
// 看起来像菜单配错了，实际只是窗口太窄导致的折叠。这个坑我踩过一次。
await evalJs(`(() => {
  const app = document.querySelector('#app').__vue_app__;
  const st = app?.config.globalProperties?.$pinia?.state?.value?.app;
  if (st && st.sidebar) st.sidebar.opened = true;
  return !!(st && st.sidebar);
})()`)
await sleep(1200)

try {
  // 三步走：先直接找叶子菜单项；找不到就展开父级目录再找；再不行去弹层里找。
  //
  // ⚠️ 不能"抓到第一个含该文字的节点就点" —— 侧边栏里父级目录标题的文字
  // 包含所有子项的文字，先点中的往往是**目录标题**，它只展开子菜单、不跳转。
  // 现象是 menuClicked=true 却停在原页面，很容易误判成"页面进不去"。
  report.menuClicked = await evalJs(`(() => {
    const text = ${JSON.stringify(MENU)};
    // 精确匹配优先，再退回包含匹配。
    // 只做 includes 会把「密钥池」匹配到「用户密钥池」——菜单点错、页面看着"没配好"，
    // 而错在探针自己。这类同名子串在中文菜单里很常见。
    const pick = (scope) => {
      const els = [...scope.querySelectorAll('.el-menu-item')];
      return els.find(el => el.textContent.trim() === text) || els.find(el => el.textContent.trim().includes(text));
    };
    let el = pick(document.querySelector('.sidebar-container') || document);
    if (!el) el = pick(document.querySelector('.el-menu--popup') || document);
    if (!el) {
      const parent = [...document.querySelectorAll('.sidebar-container .el-sub-menu__title')]
        .find(t => t.textContent.trim().includes(text));
      if (parent) {
        parent.click();                       // 展开（在弹层里则是打开弹层）
        el = pick(document.querySelector('.sidebar-container') || document);
      }
    }
    if (!el) return false;
    el.click();
    return true;
  })()`)
  if (!report.menuClicked) report.menuError = '侧边栏里没找到菜单项（叶子项）'
} catch (e) {
  report.menuError = String(e.message)
}

await sleep(7000)

// ------------------------------------------------------------- 采集渲染结果
try {
  const probe = await evalJs(`(() => {
    const iframe = document.querySelector('.app-main iframe, iframe');
    let frameText = null;
    if (iframe) {
      try { frameText = (iframe.contentDocument?.body?.innerText || '').slice(0, 1200); }
      catch (e) { frameText = '(跨域，读不到)'; }
    }
    const main = document.querySelector('.app-main') || document.body;
    return {
      url: location.href,
      frameSrc: iframe ? iframe.getAttribute('src') : null,
      frameText,
      contentText: (main.innerText || '').replace(/\\s+/g, ' ').slice(0, 1500),
      toasts: window.__toasts || []
    };
  })()`)
  Object.assign(report, probe)
} catch (e) {
  report.probeError = String(e.message)
}

// ---------------------------------------------- 可选：点开「新增授权」数节点下拉
// 节点鉴权页取节点列表失败时，页面本身看着正常（列表是另一支接口），
// 只有把新增授权的下拉点开，才知道节点到底有没有取到。
if (process.argv.includes('--probe-grant')) {
  try {
    await evalJs(`(() => {
      [...document.querySelectorAll('button')].find(b => b.textContent.includes('新增授权'))?.click();
      return true;
    })()`)
    await sleep(1200)
    // 弹窗里第一个 el-select 就是「节点」
    await evalJs(`(() => {
      const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null);
      const sel = dlg?.querySelector('.el-select');
      sel?.querySelector('.el-select__wrapper, .el-input__inner')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      sel?.click();
      return true;
    })()`)
    await sleep(1200)
    report.grantNodeOptions = await evalJs(`(() => {
      const dlg = [...document.querySelectorAll('.el-dialog')].find(d => d.offsetParent !== null);
      const sel = dlg?.querySelector('.el-select');
      return [...document.querySelectorAll('.el-select-dropdown__item')]
        .filter(i => i.offsetParent !== null)
        .map(i => i.innerText.trim());
    })()`)
  } catch (e) {
    report.grantProbeError = String(e.message)
  }
  const shot2 = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(OUT.replace(/\.png$/, '-grant.png'), Buffer.from(shot2.data, 'base64'))
}

const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
writeFileSync(OUT, Buffer.from(shot.data, 'base64'))

console.log(JSON.stringify(report, null, 2))
ws.close()
process.exit(0)