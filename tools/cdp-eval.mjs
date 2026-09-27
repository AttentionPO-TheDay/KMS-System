/**
 * 在真浏览器里执行一段 JS 并打印结果（CDP）。
 *
 * 用途：页面"看起来不对"但接口 200 时，唯一可靠的判据是在**页面自身的上下文**里
 * 发同一个请求 —— 这样 axios 拦截器、baseURL、令牌头、同源策略都参与进来，
 * 与 curl 的结论经常不一样（这一次就是）。
 *
 * 用法:
 *   node tools/cdp-eval.mjs --url http://127.0.0.1/updatedel/distchain/nodes --expr "fetch('/x').then(r=>r.status)"
 */
const argv = process.argv.slice(2)
function arg(name, dflt) {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 ? argv[i + 1] : dflt
}
const PORT = arg('port', '9222')
const URL_ = arg('url', 'about:blank')
const EXPR = arg('expr', 'location.href')
const WAIT = Number(arg('wait', '3000'))

const base = `http://127.0.0.1:${PORT}`
// 默认新开标签页执行。理由：浏览器里往往留着上一次验证的标签，
// `find(t => t.type === 'page')` 抓到的是哪一张并不确定 ——
// 我因此读错过一次页面内容（以为 A 页被重定向到了 B 页，其实是读到了 B 标签）。
const FRESH = !argv.includes('--reuse-tab')
let target
if (FRESH) {
  const r = await fetch(`${base}/json/new?about:blank`, { method: 'PUT' })
  target = r.ok ? await r.json() : null
}
if (!target) {
  const list = await (await fetch(`${base}/json/list`)).json()
  target = list.find((t) => t.type === 'page')
}

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

await new Promise((res) => ws.addEventListener('open', res, { once: true }))
await send('Page.enable')
await send('Runtime.enable')

// 视口可指定：布局类问题几乎都跟宽度有关，用默认的窄窗口测会"看起来是好的"。
const W = Number(arg('width', '1600'))
const H = Number(arg('height', '1000'))
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false })
if (URL_ && URL_ !== 'about:blank') {
  await send('Page.navigate', { url: URL_ })
  await sleep(WAIT)
}
const r = await send('Runtime.evaluate', {
  expression: `(async () => { try { return JSON.stringify(await (${EXPR}), null, 1) } catch (e) { return 'JS异常: ' + (e && e.message) } })()`,
  returnByValue: true,
  awaitPromise: true
})
console.log(r.result?.value ?? JSON.stringify(r, null, 1))

// 可选截图：布局问题光看 DOM 数字判断不了，得看图
const SHOT = arg('shot', '')
if (SHOT) {
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const { writeFileSync } = await import('node:fs')
  writeFileSync(SHOT, Buffer.from(shot.data, 'base64'))
  console.log('[shot] ' + SHOT)
}

// 自己开的标签自己收掉，免得越积越多、下次又抓到残留页
if (FRESH && target.id) {
  await fetch(`${base}/json/close/${target.id}`).catch(() => {})
}
ws.close()
process.exit(0)