// =============================================================================
// verify-node-device-auth.mjs —— 节点设备凭据认证（文档 §3 / §5）端到端验证
// -----------------------------------------------------------------------------
// 用真实浏览器完成：管理员建节点 → 拿激活凭证 → 节点激活 → 挑战-应答登录。
// 全都是**真的**：真的 WebCrypto 非导出密钥、真的 ECDSA 签名、真的服务端验签。
//
// 判据是"节点能不能拿到令牌并进站"，不是"接口返回 200"——
// 令牌是这一整套机制的唯一产出，拿不到令牌再多 200 也没意义。
//
// 用法：
//   node tools/verify-node-device-auth.mjs
//   node tools/verify-node-device-auth.mjs --node-id Node-001
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const argv = process.argv.slice(2)
const option = (name, fallback = '') => {
  const inline = argv.find((v) => v.startsWith(`--${name}=`))
  if (inline) return inline.slice(name.length + 3)
  const i = argv.indexOf(`--${name}`)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}

const ORIGIN = option('origin', 'http://127.0.0.1').replace(/\/$/, '')
const BASE = option('base', '/updatedel')
const API = option('api', '/lifecycle-api')
const PQKDS = option('pqkds', '/pqkds-api')
const CDP_PORT = Number(option('cdp-port', '9341'))
const NODE_ID = option('node-id', `Node-AUTH-${Date.now().toString(36).toUpperCase().slice(-6)}`)
const ADMIN_USER = option('admin-user', 'admin')
const ADMIN_PASS = option('admin-pass', 'admin123')

const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function captcha(uuid) {
  const raw = execFileSync('docker', ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`], { encoding: 'utf8' }).trim()
  return raw ? raw.replace(/^"(.*)"$/s, '$1') : ''
}

const dir = mkdtempSync(join(tmpdir(), 'devauth-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e) => (await rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })).result?.value

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up */ }
    if (!t) await sleep(500)
  }
  if (!t) throw new Error('拿不到 CDP page target')
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)

  // ---- 1. 管理员登录取令牌 ----
  console.log('\n== 1. 管理员登录 ==')
  const cap = await ev(`fetch('${API}/captchaImage').then(r=>r.json())`)
  const adminLogin = await ev(`fetch('${API}/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:${JSON.stringify(ADMIN_USER)},password:${JSON.stringify(ADMIN_PASS)},
    code:${JSON.stringify(captcha(cap.uuid))},uuid:${JSON.stringify(cap.uuid)}})}).then(r=>r.json())`)
  check('管理员拿到令牌', Boolean(adminLogin?.token), adminLogin?.msg || '')
  if (!adminLogin?.token) throw new Error('管理员登录失败，无法继续')
  const adminToken = adminLogin.token

  // ---- 2. 建节点 → 拿一次性激活凭证 ----
  console.log(`\n== 2. 创建节点 ${NODE_ID} ==`)
  const reg = await ev(`fetch('${PQKDS}/nodes/register/',{method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer ${adminToken}'},
    body:JSON.stringify({node_id:${JSON.stringify(NODE_ID)},name:${JSON.stringify(NODE_ID)},
      ip_address:'127.0.0.1',port:0,node_type:'validator',permission_level:'L2',domain_id:'domain-1'})}).then(r=>r.json())`)
  const regData = reg?.data || {}
  check('节点创建成功', reg?.code === 200 || reg?.code === 2000, reg?.msg || '')
  check('返回了一次性激活凭证', Boolean(regData.activation_code),
    regData.activation_code ? `凭证长度 ${String(regData.activation_code).length}` : '（为空 → 签发失败）')
  if (!regData.activation_code) throw new Error('没拿到激活凭证，后续无法进行')
  const activationCode = regData.activation_code

  // ---- 3. 节点激活：本机生成设备密钥 → 上报公钥 → 换令牌 ----
  console.log('\n== 3. 节点激活（本机生成设备密钥 + 上报公钥）==')
  // 页面里没有直接引用 device-credential 模块的入口，所以在页面内**就地**
  // 用 WebCrypto 生成同一套密钥（P-256，extractable=false），
  // 这正是节点端 `ensureDeviceKey()` 会做的事。密钥挂在全局供后续签名复用。
  const gen = await ev(`(async () => {
    const kp = await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'}, false, ['sign','verify'])
    window.__devKp = kp
    const jwk = await crypto.subtle.exportKey('jwk', kp.publicKey)
    return {kty:jwk.kty, crv:jwk.crv, hasX:!!jwk.x, hasY:!!jwk.y, dPresent:!!jwk.d}
  })()`)
  check('生成了 P-256 设备密钥（私钥不可导出）',
    gen?.kty === 'EC' && gen?.crv === 'P-256' && gen?.hasX && gen?.hasY,
    JSON.stringify(gen))

  const actRes = await ev(`(async () => {
    const jwk = await crypto.subtle.exportKey('jwk', window.__devKp.publicKey)
    const res = await fetch('${PQKDS}/node-self/activate/', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nodeId:${JSON.stringify(NODE_ID)},code:${JSON.stringify(activationCode)},
        devicePublicKey:jwk,deviceAlgorithm:'ECDSA-P256'})})
    return await res.json()
  })()`)
  check('激活成功并拿到登录令牌', Boolean(actRes?.data?.token), actRes?.msg || '')
  const firstToken = actRes?.data?.token

  // ---- 4. 凭证一次性：同一张再用必失败 ----
  console.log('\n== 4. 激活凭证的一次性 ==')
  const reuse = await ev(`(async () => {
    const jwk = await crypto.subtle.exportKey('jwk', window.__devKp.publicKey)
    const res = await fetch('${PQKDS}/node-self/activate/', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nodeId:${JSON.stringify(NODE_ID)},code:${JSON.stringify(activationCode)},
        devicePublicKey:jwk,deviceAlgorithm:'ECDSA-P256'})})
    return await res.json()
  })()`)
  check('同一凭证第二次使用被拒绝', !reuse?.data?.token, reuse?.msg || '（竟然又成功了）')

  // ---- 5. 挑战-应答登录 ----
  console.log('\n== 5. 挑战-应答登录 ==')
  const loginFlow = await ev(`(async () => {
    const chRes = await fetch('${PQKDS}/node-self/challenge/?nodeId=' + encodeURIComponent(${JSON.stringify(NODE_ID)}))
    const ch = await chRes.json()
    if (!ch?.data?.challenge) return {step:'challenge', ok:false, msg:ch?.msg}
    const sig = await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'}, window.__devKp.privateKey,
      new TextEncoder().encode(ch.data.challenge))
    const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    const lgRes = await fetch('${PQKDS}/node-self/login/', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nodeId:${JSON.stringify(NODE_ID)},challengeId:ch.data.challengeId,signature:b64})})
    const lg = await lgRes.json()
    return {step:'login', ok:!!lg?.data?.token, msg:lg?.msg, token:lg?.data?.token, sigLen:new Uint8Array(sig).length}
  })()`)
  check('签名长度为 raw r||s 64 字节', loginFlow?.sigLen === 64, `实际 ${loginFlow?.sigLen}`)
  check('挑战-应答登录拿到令牌', loginFlow?.ok === true, loginFlow?.msg || '')
  const deviceToken = loginFlow?.token

  // ---- 6. 挑战一次性（防重放）----
  console.log('\n== 6. 挑战防重放 ==')
  const replay = await ev(`(async () => {
    const chRes = await fetch('${PQKDS}/node-self/challenge/?nodeId=' + encodeURIComponent(${JSON.stringify(NODE_ID)}))
    const ch = await chRes.json()
    const sig = await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'}, window.__devKp.privateKey,
      new TextEncoder().encode(ch.data.challenge))
    const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    const body = JSON.stringify({nodeId:${JSON.stringify(NODE_ID)},challengeId:ch.data.challengeId,signature:b64})
    const first = await (await fetch('${PQKDS}/node-self/login/',{method:'POST',headers:{'Content-Type':'application/json'},body})).json()
    const second = await (await fetch('${PQKDS}/node-self/login/',{method:'POST',headers:{'Content-Type':'application/json'},body})).json()
    return {firstOk:!!first?.data?.token, secondOk:!!second?.data?.token, secondMsg:second?.msg}
  })()`)
  check('第一次用该挑战成功', replay?.firstOk === true)
  check('同一挑战重放被拒绝', replay?.secondOk === false, replay?.secondMsg || '（竟然又成功了）')

  // ---- 7. 错误签名必须失败 ----
  console.log('\n== 7. 错误签名必须失败 ==')
  const wrongSig = await ev(`(async () => {
    // 另生成一把**不同的**密钥来签 —— 模拟"不是那台设备"
    const other = await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'}, false, ['sign','verify'])
    const ch = await (await fetch('${PQKDS}/node-self/challenge/?nodeId=' + encodeURIComponent(${JSON.stringify(NODE_ID)}))).json()
    const sig = await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'}, other.privateKey,
      new TextEncoder().encode(ch.data.challenge))
    const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    const res = await (await fetch('${PQKDS}/node-self/login/',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nodeId:${JSON.stringify(NODE_ID)},challengeId:ch.data.challengeId,signature:b64})})).json()
    return {ok:!!res?.data?.token, msg:res?.msg}
  })()`)
  check('非登记设备的签名被拒绝', wrongSig?.ok === false, wrongSig?.msg || '（竟然通过了！）')

  // ---- 8. 令牌真的能进站 ----
  console.log('\n== 8. 令牌可用性（能读 getInfo / getRouters）==')
  if (deviceToken) {
    const whoami = await ev(`(async () => {
      const res = await fetch('${API}/getInfo', {headers:{'Authorization':'Bearer ${deviceToken}'}})
      const j = await res.json()
      return {code:j.code, userId:j.user?.userId, name:j.user?.userName,
              principalType:j.user?.principalType, roleLevel:j.user?.roleLevel}
    })()`)
    check('设备令牌能读到 getInfo', whoami?.code === 200, JSON.stringify(whoami))
    check('身份是 NODE 主体', String(whoami?.principalType).toUpperCase() === 'NODE',
      String(whoami?.principalType))
  } else {
    check('设备令牌可用', false, '没有令牌可测')
  }

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.p)
  console.log(`总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  process.exitCode = failed.length ? 1 : 0
} catch (e) {
  console.error('\n[ERROR]', e.message)
  process.exitCode = 1
} finally {
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}
