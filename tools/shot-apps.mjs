/**
 * 截图对比各前端的实际观感。
 * 用法: node tools/shot-apps.mjs [cdpPort] [outDir]
 */
import { writeFileSync, mkdirSync } from 'node:fs'

const port = process.argv[2] || '9222'
const outDir = process.argv[3] || 'kms-ops/tests/out'
mkdirSync(outDir, { recursive: true })
const CDP = `http://127.0.0.1:${port}`
const ORIGIN = 'http://127.0.0.1'

let target
try { target = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json() }
catch { target = await (await fetch(`${CDP}/json/new?about:blank`)).json() }

const ws = new WebSocket(target.webSocketDebuggerUrl)
let n = 0
const pending = new Map()
const consoleErrors = []
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  } else if (m.method === 'Runtime.exceptionThrown') {
    consoleErrors.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text || '').split('\n')[0])
  } else if (m.method === 'Network.responseReceived' && m.params.response.status >= 400) {
    consoleErrors.push(`HTTP ${m.params.response.status} ${m.params.response.url.replace(ORIGIN, '')}`)
  }
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++n; pending.set(i, { resolve: res, reject: rej })
  ws.send(JSON.stringify({ id: i, method, params }))
})
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Network.clearBrowserCache')
await send('Emulation.setDeviceMetricsOverride', { width: 1500, height: 950, deviceScaleFactor: 1, mobile: false })
const evalJs = async (e) => {
  const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })
  return r.exceptionDetails ? { __err: r.exceptionDetails.exception?.description } : r.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const shot = async (name) => {
  const s = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(`${outDir}/${name}.png`, Buffer.from(s.data, 'base64'))
  console.log(`  截图 → ${outDir}/${name}.png`)
}

const probe = async (name, url, waitMs, extra) => {
  consoleErrors.length = 0
  console.log(`\n=== ${name} ===`)
  await send('Page.navigate', { url })
  await sleep(waitMs)
  if (extra) await extra()
  console.log('  pathname:', await evalJs('location.pathname'))
  console.log('  首屏文本:', String(await evalJs(
    `document.body.innerText.split('\\n').map(s=>s.trim()).filter(Boolean).slice(0,10).join(' | ')`
  )).slice(0, 300))
  // 关键 CSS 变量的实际解析值（decision: 令牌是否真的生效）
  console.log('  解析后的关键变量:', JSON.stringify(await evalJs(`(() => {
    const cs = getComputedStyle(document.documentElement)
    const keys = ['--kms-brand','--kms-brand-fill','--kms-surface-page','--kms-text-primary',
                  '--el-color-primary','--el-text-color-placeholder','--el-text-color-regular',
                  '--el-font-size-base','--el-border-color']
    const o = {}
    for (const k of keys) o[k] = cs.getPropertyValue(k).trim() || '(未定义)'
    o['body.fontFamily'] = getComputedStyle(document.body).fontFamily.slice(0, 70)
    o['body.background'] = getComputedStyle(document.body).backgroundColor
    o['html.class'] = document.documentElement.className
    return o
  })()`)))
  if (consoleErrors.length) console.log('  ⚠ 报错:', JSON.stringify([...new Set(consoleErrors)].slice(0, 6)))
  else console.log('  ✓ 无报错')
  await shot(name)
}

await probe('distribute-login', `${ORIGIN}/distribute/`, 7000)
await probe('updatedel-login', `${ORIGIN}/updatedel/login`, 6000)
await probe('user-login', `${ORIGIN}/user/login`, 6000)

ws.close()
process.exit(0)
