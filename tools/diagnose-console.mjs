/**
 * 用真浏览器打开 /updatedel/，抓控制台错误与页面状态。
 *
 * 为什么必须用真浏览器：curl 拿到的是 200 和正确的 MIME，
 * 但 SPA 是在**运行时**才失败的 —— 一个删掉的模块、一个写错的导入，
 * 都只在 JS 执行时才暴露，而 HTTP 层面看不出来。
 */
import { spawn, execSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find(existsSync)
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const PORT = 9223
const dir = mkdtempSync(join(tmpdir(), 'kms-cdp-'))
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'
], { stdio: 'ignore' })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  // 等 CDP 起来
  let ws = null
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`)
      const tabs = await r.json()
      const page = tabs.find((t) => t.type === 'page')
      if (page?.webSocketDebuggerUrl) { ws = page.webSocketDebuggerUrl; break }
    } catch { /* 还没起来 */ }
    await sleep(250)
  }
  if (!ws) { console.log('CDP 未就绪'); process.exit(1) }

  const { WebSocket } = await import('ws').catch(() => ({ WebSocket: null }))
  // 没有 ws 包就用 node 原生（Node 22+ 有全局 WebSocket）
  const WS = WebSocket || globalThis.WebSocket
  if (!WS) { console.log('没有可用的 WebSocket 实现'); process.exit(1) }

  const sock = new WS(ws)
  let id = 0
  const pending = new Map()
  const logs = []
  const errors = []

  sock.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return }
    if (msg.method === 'Runtime.consoleAPICalled') {
      const text = (msg.params.args || []).map((a) => a.value ?? a.description ?? a.type).join(' ')
      logs.push(`[${msg.params.type}] ${text}`)
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      errors.push(d.exception?.description || d.text || JSON.stringify(d).slice(0, 300))
    }
    if (msg.method === 'Log.entryAdded') {
      const e = msg.params.entry
      if (e.level === 'error') errors.push(`[${e.source}] ${e.text} ${e.url ? '@ ' + e.url : ''}`)
    }
  })

  const send = (method, params = {}) => new Promise((resolve) => {
    const mid = ++id
    pending.set(mid, resolve)
    sock.send(JSON.stringify({ id: mid, method, params }))
  })

  sock.addEventListener('open', async () => {
    await send('Runtime.enable')
    await send('Log.enable')
    await send('Page.enable')
    // ⚠️ **不要 await Page.navigate 的响应**。
    //    实测它会偶发不返回，整个脚本挂死在那一行、零输出 ——
    //    看起来像"页面加载不出来"，实际是工具卡住了。
    //    本仓库的 `tools/cdp-eval.mjs` 注释里也记着同一条。
    //    这里发出去就不管，靠下面的 sleep 等页面自己加载完。
    sock.send(JSON.stringify({ id: ++id, method: 'Page.navigate', params: { url: 'http://127.0.0.1/updatedel/' } }))
    await sleep(8000)

    const res = await send('Runtime.evaluate', {
      expression: `JSON.stringify({
        url: location.href,
        title: document.title,
        bodyLen: (document.body?.innerText || '').length,
        bodyHead: (document.body?.innerText || '').slice(0, 200),
        appHtmlLen: (document.querySelector('#app')?.innerHTML || '').length,
        scripts: [...document.scripts].map(s => s.src).filter(Boolean)
      })`,
      returnByValue: true
    })
    console.log('\n=== 页面状态 ===')
    try {
      const v = JSON.parse(res.result.result.value)
      console.log('  URL:', v.url)
      console.log('  标题:', v.title)
      console.log('#app 内容长度:', v.appHtmlLen)
      console.log('  可见文字长度:', v.bodyLen)
      console.log('  可见文字片段:', JSON.stringify(v.bodyHead))
      console.log('  已加载脚本数:', v.scripts.length)
      v.scripts.forEach((s) => console.log('    ', s))
    } catch (e) {
      console.log('  解析失败:', JSON.stringify(res).slice(0, 300))
    }

    console.log('\n=== 控制台错误 ===')
    if (!errors.length) console.log('  （无）')
    errors.slice(0, 12).forEach((e) => console.log('  ✗', String(e).split('\n').slice(0, 4).join('\n     ')))

    console.log('\n=== 控制台日志（最后 15 条）===')
    logs.slice(-15).forEach((l) => console.log('  ', l.slice(0, 220)))

    sock.close()
    proc.kill()
    process.exit(0)
  })
}

main().catch((e) => { console.error(e); proc.kill(); process.exit(1) })
