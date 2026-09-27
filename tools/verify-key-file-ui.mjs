#!/usr/bin/env node
import { captchaFields } from './lib/captcha.mjs'
/**
 * 密钥文件导入的浏览器端验收（计划 §7 P3 步骤 0b）
 * =============================================================================
 * 前面的 `tools/verify-key-file.mjs` 测的是**格式与校验逻辑**（纯函数）。
 * 这里测的是**真的接到界面上之后还成立**：
 *   - 合规文件 → 提示成功、密钥环计数增加、写入 localStorage；
 *   - 被篡改的文件 → 明确报错，且**密钥环不变**（绝不能悄悄把错的存进去）；
 *   - 刷新页面后仍在（说明真的持久化了，而不是只活在内存里）。
 *
 * 做法：用 CDP 打开用户前台的密钥生成页，直接给文件选择框塞内容
 * （通过 DataTransfer 构造 File 对象），再读界面上的提示文案。
 *
 * 用法：node tools/verify-key-file-ui.mjs [cdpPort] [origin]
 * =============================================================================
 */

const CDP_PORT = process.argv[2] || '9222'
const ORIGIN = process.argv[3] || 'http://127.0.0.1'
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

// ---------------------------------------------------------------------------
// CDP 接线
// ---------------------------------------------------------------------------
let target
try {
  target = await (await fetch(`${CDP}/json/new?about:blank`, { method: 'PUT' })).json()
} catch {
  target = await (await fetch(`${CDP}/json/new?about:blank`)).json()
}
if (!target?.webSocketDebuggerUrl) throw new Error('无法新建 CDP 标签页')

const ws = new WebSocket(target.webSocketDebuggerUrl)
let msgId = 0
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
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
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Page.enable', {})
await send('Runtime.enable', {})

const evalJs = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) {
    throw new Error(r.exceptionDetails.text + ' :: ' + (r.exceptionDetails.exception?.description || ''))
  }
  return r.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

console.log(`\n=== 密钥文件导入 UI 验收 @ ${ORIGIN} ===\n`)

// ---------------------------------------------------------------------------
// 登录 + 打开生成页
// ---------------------------------------------------------------------------
await send('Page.navigate', { url: `${ORIGIN}/user/login` })
await sleep(3000)
const gotToken = await evalJs(`(async () => {
  const res = await fetch('/lifecycle-api/login', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ username:'yx', password:'admin123', ...${JSON.stringify(await captchaFields(ORIGIN))} }) })
  const j = await res.json()
  if (j.token) document.cookie = 'Admin-Token=' + j.token + '; path=/'
  return !!j.token
})()`)
if (!gotToken) throw new Error('登录失败')

await send('Page.navigate', { url: `${ORIGIN}/user/generate/index` })
await sleep(6000)

// 从干净状态开始（避免上一轮残留影响"密钥环不变"的断言）
await evalJs(`(() => { localStorage.removeItem('kms-user-keyring-v1'); return true })()`)
await send('Page.reload', { ignoreCache: true })
await sleep(6000)

const hasImportUi = await evalJs(`document.body.innerText.includes('导入密钥文件')`)
check('生成页出现「导入密钥文件」入口', hasImportUi)

// ---------------------------------------------------------------------------
// 构造一份密钥文件（校验和用页面自己的 WebCrypto 算，确保与实现一致）
// ---------------------------------------------------------------------------
const makeFile = async (tamper) => {
  const script = `(async () => {
    const fields = {
      version: 1, kind: 'kms-user-key', key_id: '9001', user_id: '2',
      algorithm: 'SM2', created_at: '2026-09-24T00:00:00.000Z',
      private_share: '${'a'.repeat(63)}1', public_key: '04${'b'.repeat(128)}'
    }
    const canonical = JSON.stringify(Object.fromEntries(
      ['version','kind','key_id','user_id','algorithm','created_at','private_share','public_key']
        .map(k => [k, String(fields[k] ?? '')])))
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical))
    const hex = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2,'0')).join('')
    const file = { ...fields, checksum: 'sha256:' + hex }
    ${tamper ? "file.private_share = 'c'.repeat(64)" : ''}
    return JSON.stringify(file)
  })()`
  return evalJs(script)
}

const goodFile = await makeFile(false)
const badFile = await makeFile(true)

/** 把内容塞进导入弹窗的"粘贴内容"页签并点导入 */
const importViaPaste = async (content) => {
  return evalJs(`(async () => {
    const sleep = (ms) => new Promise(r => setTimeout(r, ms))
    // 打开弹窗
    const btn = [...document.querySelectorAll('button')].find(b => b.innerText.includes('导入密钥文件'))
    if (!btn) return { error: '找不到导入按钮' }
    btn.click()
    await sleep(900)
    // 切到"粘贴内容"页签
    const tab = [...document.querySelectorAll('.el-tabs__item')].find(t => t.innerText.includes('粘贴内容'))
    if (!tab) return { error: '找不到粘贴内容页签' }
    tab.click()
    await sleep(500)
    const ta = document.querySelector('.el-dialog textarea')
    if (!ta) return { error: '找不到文本域' }
    // Vue 受控组件：必须派发 input 事件，直接赋值不会更新 v-model
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    setter.call(ta, ${JSON.stringify(content)})
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    await sleep(400)
    const importBtn = [...document.querySelectorAll('.el-dialog button')].find(b => b.innerText.trim() === '导入')
    if (!importBtn) return { error: '找不到导入按钮（弹窗内）' }
    importBtn.click()
    await sleep(1500)
    const dialog = document.querySelector('.el-dialog:not([style*="display: none"])')
    // 错误/成功提示各有专门的元素，直接读它们，
    // 比在整段 innerText 上正则匹配可靠得多（之前就是因为正则只截到"密钥文件"三个字）
    const errEl = dialog ? dialog.querySelector('.error-text') : null
    const okEl = dialog ? dialog.querySelector('.success-text') : null
    return {
      errorText: errEl ? errEl.innerText.trim() : '',
      successText: okEl ? okEl.innerText.trim() : '',
      ring: JSON.parse(localStorage.getItem('kms-user-keyring-v1') || '{}')
    }
  })()`)
}

// ---------------------------------------------------------------------------
console.log('1. 合规文件：应导入成功并落进密钥环')
{
  const r = await importViaPaste(goodFile)
  if (r.error) {
    check('导入合规文件', false, r.error)
  } else {
    check('提示导入成功', String(r.successText).includes('已导入'), r.successText || '(无成功提示)')
    check('写入 localStorage（真的持久化了，不是只活在内存）',
      Boolean(r.ring['9001']), `密钥环 keys=${Object.keys(r.ring).join(',') || '(空)'}`)
    check('存下来的私钥份额与文件一致',
      r.ring['9001']?.private_share === 'a'.repeat(63) + '1')
  }
}

console.log('\n2. 被篡改的文件：必须明确报错，且**密钥环不变**')
{
  const before = await evalJs(`JSON.stringify(JSON.parse(localStorage.getItem('kms-user-keyring-v1') || '{}'))`)
  const r = await importViaPaste(badFile)
  if (r.error) {
    check('导入被篡改文件', false, r.error)
  } else {
    check('明确报出校验和不匹配', String(r.errorText).includes('校验和不匹配'),
      r.errorText || '(未捕获到 .error-text 元素)')
    const after = await evalJs(`JSON.stringify(JSON.parse(localStorage.getItem('kms-user-keyring-v1') || '{}'))`)
    check('★ 密钥环没有被污染（错的密钥绝不会悄悄存进去）', before === after)
  }
}

console.log('\n3. 刷新页面后仍在（持久化有效）')
{
  await send('Page.navigate', { url: `${ORIGIN}/user/generate/index` })
  await sleep(6000)
  const persisted = await evalJs(`Object.keys(JSON.parse(localStorage.getItem('kms-user-keyring-v1') || '{}')).length`)
  check('重新加载后密钥仍在密钥环里', persisted === 1, `条数=${persisted}`)
  const badge = await evalJs(`document.body.innerText.includes('已导入 1 把')`)
  check('界面显示「已导入 1 把」', badge)
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
ws.close()
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('密钥文件导入在界面上行为正确。\n')