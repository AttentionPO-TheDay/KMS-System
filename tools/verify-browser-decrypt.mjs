#!/usr/bin/env node
/**
 * 浏览器端解封的端到端验收（P3 收尾）。
 *
 * 这是"用户真的能解开信封"的最终检查，覆盖纯函数测不到的部分：
 *   密钥文件 → 本机密钥环 → 页面上的「解开」按钮 → 显示密钥 + 指纹一致。
 *
 * 样本由 `_mk_browser_sample.py` 产出（已知 d_A + 已分发的信封），
 * 通过环境变量 `BROWSER_DECRYPT_SAMPLE` 传入样本文件路径。
 *
 * 用法：node tools/verify-browser-decrypt.mjs <sample.json> [cdpPort]
 */
import { captchaFields } from './lib/captcha.mjs'
import { readFileSync } from 'node:fs'

const samplePath = process.argv[2]
const CDP_PORT = process.argv[3] || '9222'
if (!samplePath) {
  console.error('用法: node tools/verify-browser-decrypt.mjs <sample.json> [cdpPort]')
  process.exit(2)
}
const SAMPLE = JSON.parse(readFileSync(samplePath, 'utf8'))
const CDP = `http://127.0.0.1:${CDP_PORT}`

let pass = 0
let fail = 0
const failures = []
const check = (name, ok, detail = '') => {
  if (ok) {
    pass++
    console.log(`  [OK]   ${name}${detail ? '  ' + detail : ''}`)
  } else {
    fail++
    failures.push(name)
    console.log(`  [FAIL] ${name}${detail ? '  ' + detail : ''}`)
  }
}

const target = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json()
const ws = new WebSocket(target.webSocketDebuggerUrl)
let msgId = 0
const pending = new Map()
const consoleErrors = []
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
    consoleErrors.push((m.params.args || []).map((a) => a.value || '').join(' ').slice(0, 120))
  }
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id)
    pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  }
})
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const i = ++msgId
    pending.set(i, { resolve: res, reject: rej })
    ws.send(JSON.stringify({ id: i, method, params }))
  })
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
await send('Page.enable')
await send('Runtime.enable')

const evalJs = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) {
    throw new Error(r.exceptionDetails.text + ' :: ' + (r.exceptionDetails.exception?.description || ''))
  }
  return r.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

console.log('\n=== 浏览器端解封端到端验收 ===\n')

await send('Page.navigate', { url: 'http://127.0.0.1/user/login' })
await sleep(2800)
await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'yx', password:'admin123', ...${JSON.stringify(await captchaFields('http://127.0.0.1'))} }) })
  const j = await res.json()
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/'
  return !!j.token
})()`)

await send('Page.navigate', { url: 'http://127.0.0.1/user/symmetric-keys/index' })
await sleep(7000)

// 注入密钥文件（模拟用户在「导入密钥文件」里导入自己的文件）。
// 校验和算法必须与 utils/key-file.js 完全一致：固定字段顺序 + 紧凑 JSON。
const injected = await evalJs(`(() => {
  const S = ${JSON.stringify(SAMPLE)}
  const ORDER = ['version','kind','key_id','user_id','algorithm','created_at','private_share','public_key']
  const fields = {
    version: 1, kind: 'kms-user-key', key_id: String(S.keyId), user_id: String(S.userId),
    algorithm: 'SM2', created_at: new Date().toISOString(),
    private_share: S.privateShare, public_key: S.publicKey
  }
  const canonical = JSON.stringify(Object.fromEntries(ORDER.map((k) => [k, String(fields[k] ?? '')])))
  return crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical)).then((d) => {
    const hex = [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('')
    const file = { ...fields, checksum: 'sha256:' + hex }
    localStorage.setItem('kms-user-keyring-v1', JSON.stringify({ [String(S.keyId)]: file }))
    return true
  })
})()`)
check('密钥文件已注入本机密钥环', injected === true)

await send('Page.reload', { ignoreCache: true })
await sleep(8000)

const rows = await evalJs(`document.querySelectorAll('.el-table__row').length`)
check('信封列表有数据', rows > 0, `${rows} 行`)

const clicked = await evalJs(`(() => {
  const btn = [...document.querySelectorAll('.el-table__row button')].find((b) => b.innerText.trim() === '解开')
  if (!btn) return 'no-button'
  if (btn.disabled) return 'disabled'
  btn.click()
  return 'clicked'
})()`)
check('「解开」按钮可用并被点击', clicked === 'clicked', clicked)

await sleep(7000)
const txt = await evalJs('document.body.innerText')

check('★ 页面出现解密结果', txt.includes('已用本机密钥解开'))
check('★ 指纹与库中记录一致（解出的正是那把密钥）', txt.includes('指纹一致'))
check('显示的是 32 位十六进制的 SM4 密钥', /[0-9a-f]{32}/.test(txt))
check('没有出现解密错误提示', !txt.includes('解封失败') && !txt.includes('完整性校验失败'))
check('无 console 错误', consoleErrors.length === 0, consoleErrors.slice(0, 2).join(' | '))

ws.close()
console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('用户能在浏览器里用自己的密钥文件解开信封。\n')
