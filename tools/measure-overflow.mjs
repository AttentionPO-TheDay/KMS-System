// 测量页面横向溢出：在指定宽度下找出把页面撑宽的元素。
// 用法：node tools/measure-overflow.mjs <user|admin> <path> [width]
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'

const target = process.argv[2] || 'user'
const path = process.argv[3] || '/user/lifecycle/index'
const width = Number(process.argv[4] || 1366)
const ORIGIN = 'http://127.0.0.1'
const CDP_PORT = 9226
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const dir = mkdtempSync(join(tmpdir(), 'ovf-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', `--window-size=${width},900`, 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const rpc = (method, params = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.id === n) { ws.removeEventListener('message', on); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method, params }))
})
const ev = async (expr) => (await rpc('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.value

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
    if (!t) await sleep(500)
  }
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable')

  const cred = target === 'admin' ? ['admin', '/updatedel-api'] : ['yx', '/lifecycle-api']
  const token = await login(ORIGIN, cred[1], cred[0], 'admin123')
  await rpc('Page.navigate', { url: `${ORIGIN}/user/` }); await sleep(2500)
  await ev(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${path}` }); await sleep(9000)

  const report = await ev(`(() => {
    const de = document.documentElement
    const vw = de.clientWidth
    const wide = []
    document.querySelectorAll('*').forEach((el) => {
      const r = el.getBoundingClientRect()
      if (r.width > vw + 1) {
        wide.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className && typeof el.className === 'string' ? el.className : '').slice(0, 70),
          width: Math.round(r.width),
          left: Math.round(r.left),
          scrollW: el.scrollWidth
        })
      }
    })
    // 只留最外层几个，避免几十层嵌套刷屏
    return {
      viewport: vw,
      docScrollWidth: de.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      hasHorizontalScroll: de.scrollWidth > vw,
      widest: wide.sort((a, b) => b.width - a.width).slice(0, 12)
    }
  })()`)
  console.log(JSON.stringify(report, null, 1))
} catch (e) {
  console.error('measure failed:', e.message)
} finally {
  try { ws?.close() } catch {}
  chrome.kill()
}
