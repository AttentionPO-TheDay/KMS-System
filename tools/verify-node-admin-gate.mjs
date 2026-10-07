// =============================================================================
// verify-node-admin-gate.mjs —— 节点管理页的「删除 / 重签凭证 / 密钥详情 / 编辑」
// -----------------------------------------------------------------------------
// 回归对象（2026-10-08 用户实测反馈「节点管理页面无法删除节点、无法重发凭证，
// 报错：身份认证信息未提供」）：
//
//   `NodeViewSet` 里这些动作在 §4.4 阶段一被移出 AllowAny 名单后交给
//   `super().get_permissions()`，而那条链在本仓配置下**恒判未认证** ——
//   `SIMPLE_JWT.AUTH_HEADER_TYPES = ('JWT',)` 与全系统的
//   `Authorization: Bearer …` 不匹配，`JWTAuthentication` 直接返回 None，
//   `request.user` 成了 AnonymousUser，`CustomPermission` 于是回
//   4000「身份认证信息未提供。」。**管理员自己也进不去**。
//
//   修法：这些动作走 `initial()` 里的 introspect 闸门（与 `/key-pool/*` 同一
//   套路），身份由 `kms_service_client.introspect` 证实。
//
// 本脚本钉住三件事，每件都从**真界面/真接口**取证：
//   1. 管理员：四个动作全部走得通（界面点 + 接口调）；
//   2. 未登录 / 非管理员令牌：必须被拒，且**理由要能照做**
//      （"未登录" / "仅管理员可执行"），不能是那句配置缺陷的兜底文案；
//   3. 反向护栏：拒绝时**不能**出现「身份认证信息未提供。」
//      —— 那句正是本轮缺陷的特征，它回来就说明闸门又接到了断掉的链上。
//
// ⚠️ 会真建一个节点、真删掉它（结尾自清）。用法：node tools/verify-node-admin-gate.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const PQKDS = `${ORIGIN}/pqkds-api/pqkds`
const PORT = 9393
const SEED = Date.now().toString(36).toUpperCase().slice(-6)
const NODE_A = `Node-GATE-A-${SEED}`  // 界面操作的靶子（管理员删除）
const NODE_B = `Node-GATE-B-${SEED}`  // 接口操作的靶子（管理员删除 + 非管理员被拒）

//: 配置缺陷的兜底文案。它在任何**预期是业务拒绝**的响应里出现 = 闸门接错了链。
const BROKEN_CHAIN_MSG = '身份认证信息未提供'

const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function captcha(uuid) {
  const raw = execFileSync('docker', ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`], { encoding: 'utf8' }).trim()
  return raw ? raw.replace(/^"(.*)"$/s, '$1') : ''
}

const dir = mkdtempSync(join(tmpdir(), 'nodegate-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
let pageCaptchaUuid = ''
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e, timeoutMs = 60000) => {
  const r = await Promise.race([
    rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true }),
    new Promise((_, j) => setTimeout(() => j(new Error('页面求值超时')), timeoutMs)),
  ])
  // ⚠️ `rpc` 已经把 CDP 的 `result` 解开了，所以这里直接读 `r.result.value`。
  //    写成 `r.result.result.value` 会**恒 undefined** —— 页面明明渲染对了，
  //    断言却全落在 undefined 上（本轮实测踩到：令牌读成空串、
  //    location.pathname 读成 undefined，看起来像"页面没打开"）。
  if (r?.exceptionDetails) return undefined
  return r?.result?.value
}
const SET = `(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}`

function hookCaptcha() {
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.method === 'Network.responseReceived' && /captchaImage/.test(m.params?.response?.url || '')) {
      rpc('Network.getResponseBody', { requestId: m.params.requestId })
        .then((r) => { try { pageCaptchaUuid = JSON.parse(r.body).uuid || '' } catch { /* 非 JSON */ } })
        .catch(() => { /* 响应体可能已被丢弃 */ })
    }
  })
}

async function loginAdmin() {
  pageCaptchaUuid = ''
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(4000)
  const inputs = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
  await ev(`(() => { const set=${SET}; const ins=${inputs}
    set(ins[0],'admin'); set(ins[1],'admin123'); set(ins[2],${JSON.stringify(captcha(pageCaptchaUuid))}); return true })()`)
  await sleep(400)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('登')); b.click(); return true })()`)
  await sleep(7000)
  return ev(`location.pathname`)
}

/** 调一个接口，回 `{code, msg, data}`（两套信封都收敛成同一形状，断言才写得干净）。 */
async function call(path, { method = 'GET', token, body } = {}) {
  const res = await fetch(`${ORIGIN}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {})
  })
  const json = await res.json().catch(() => null)
  return { code: json?.code, msg: String(json?.msg || json?.message || ''), data: json?.data, raw: json }
}

async function registerNode(token, nodeId, port) {
  return call('/pqkds-api/pqkds/nodes/register/', {
    method: 'POST', token,
    body: {
      node_id: nodeId, name: nodeId, ip_address: '127.0.0.1', port,
      node_type: 'full', permission_level: 'L2', domain_id: 'gate-verify'
    }
  })
}

async function nodePk(token, nodeId) {
  const list = await call('/pqkds-api/pqkds/nodes/?page=1&limit=500', { token })
  const rows = list.data?.results || list.data || []
  return rows.find((r) => r.node_id === nodeId)?.id
}

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up */ }
    if (!t) await sleep(500)
  }
  if (!t) throw new Error('拿不到 CDP page target')
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable'); await rpc('Network.enable')
  hookCaptcha()

  // ===== 1. 管理员登录 + 建两个靶子节点 =====
  console.log('\n== 1. 管理员登录、建靶子节点 ==')
  const adminPath = String(await loginAdmin() || '')
  check('管理员登录后进站', !adminPath.includes('/login'), adminPath || '（路径读取失败）')
  const adminToken = await ev(`document.cookie.match(/Admin-Token=([^;]+)/)?.[1] || ''`)
  check('取到管理员令牌', Boolean(adminToken), adminToken ? `长度 ${adminToken.length}` : '（空）')

  const regA = await registerNode(adminToken, NODE_A, 9500 + (Date.now() % 200))
  const regB = await registerNode(adminToken, NODE_B, 9750 + (Date.now() % 200))
  check('靶子节点 A / B 建好', regA.code === 2000 && regB.code === 2000,
    `A=${regA.code} B=${regB.code}`)
  const pkA = await nodePk(adminToken, NODE_A)
  const pkB = await nodePk(adminToken, NODE_B)
  check('取到两个节点的主键', Boolean(pkA && pkB), `pkA=${pkA} pkB=${pkB}`)
  if (!pkA || !pkB) throw new Error('没拿到主键，无法继续')

  // ===== 2. ★ 管理员：四个动作全部走得通（接口层） =====
  console.log('\n== 2. ★ 管理员走这四个动作（此前全部回「身份认证信息未提供」）==')
  const reissue = await call(`/pqkds-api/pqkds/nodes/${pkB}/reissue_activation_code/`, { method: 'POST', token: adminToken })
  check('★★ 重新签发激活凭证（管理员）', reissue.code === 2000 && Boolean(reissue.data?.activation_code),
    `code=${reissue.code} msg=${reissue.msg.slice(0, 60)}${reissue.data?.activation_code ? ` 凭证长度=${reissue.data.activation_code.length}` : ''}`)

  const keys = await call(`/pqkds-api/pqkds/nodes/${pkB}/keys/`, { token: adminToken })
  check('★ 查看节点密钥（管理员）', keys.code === 2000 && 'kyber_key_ready' in (keys.data || {}),
    `code=${keys.code} msg=${keys.msg.slice(0, 50)}`)

  const edited = await call(`/pqkds-api/pqkds/nodes/${pkB}/`, {
    method: 'PATCH', token: adminToken, body: { description: 'gate-verify' }
  })
  check('★ 编辑节点（管理员）', edited.code === 2000, `code=${edited.code} msg=${edited.msg.slice(0, 50)}`)

  // 删除放最后（删完 pkB 就没了）
  const del = await call(`/pqkds-api/pqkds/nodes/${pkB}/`, { method: 'DELETE', token: adminToken })
  check('★★ 删除节点（管理员）', del.code === 2000 && del.data?.deleted_node?.node_id === NODE_B,
    `code=${del.code} msg=${del.msg.slice(0, 60)}`)
  const gone = await nodePk(adminToken, NODE_B)
  check('★ 删除是真落库（列表里查不到了）', gone === undefined, `pk=${gone}`)

  // ===== 3. ★ 未登录：必须被拒，理由是"未登录" =====
  console.log('\n== 3. 未登录：拒绝理由必须能照做 ==')
  const anonReissue = await call(`/pqkds-api/pqkds/nodes/${pkA}/reissue_activation_code/`, { method: 'POST' })
  const anonDelete = await call(`/pqkds-api/pqkds/nodes/${pkA}/`, { method: 'DELETE' })
  const anonKeys = await call(`/pqkds-api/pqkds/nodes/${pkA}/keys/`)
  check('★ 无令牌重签被拒', anonReissue.code === 4000, `code=${anonReissue.code} msg=${anonReissue.msg.slice(0, 40)}`)
  check('★ 无令牌删除被拒', anonDelete.code === 4000, `code=${anonDelete.code} msg=${anonDelete.msg.slice(0, 40)}`)
  check('★ 无令牌看密钥被拒（密钥材料不是公开量）', anonKeys.code === 4000, `code=${anonKeys.code} msg=${anonKeys.msg.slice(0, 40)}`)
  check('★★ 拒绝理由是「未登录」，不是那句配置缺陷的兜底文案',
    anonReissue.msg.includes('未登录') && anonDelete.msg.includes('未登录')
    && ![anonReissue, anonDelete, anonKeys].some((r) => r.msg.includes(BROKEN_CHAIN_MSG)),
    `reissue="${anonReissue.msg.slice(0, 30)}" delete="${anonDelete.msg.slice(0, 30)}"`)

  // ===== 4. ★ 非管理员令牌：必须被拒，理由是"仅管理员" =====
  console.log('\n== 4. 节点令牌（非管理员）越权：必须被拒 ==')
  const act = await call('/pqkds-api/pqkds/nodes/register/', {
    method: 'POST', token: adminToken,
    body: { node_id: `Node-GATE-N-${SEED}`, name: `Node-GATE-N-${SEED}`, ip_address: '127.0.0.1',
      port: 9800 + (Date.now() % 150), node_type: 'full', permission_level: 'L2', domain_id: 'gate-verify' }
  })
  const nodeActCode = act.data?.activation_code || ''
  // 用本机设备密钥激活，拿一枚**真的节点令牌**（不是伪造的）
  const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
  const session = await lib.activateNode(`Node-GATE-N-${SEED}`, nodeActCode)
  check('取得一枚真实的节点令牌（用于越权测试）', Boolean(session?.token), `长度=${session?.token?.length || 0}`)

  const nodeReissue = await call(`/pqkds-api/pqkds/nodes/${pkA}/reissue_activation_code/`, { method: 'POST', token: session.token })
  const nodeDelete = await call(`/pqkds-api/pqkds/nodes/${pkA}/`, { method: 'DELETE', token: session.token })
  const nodeKeys = await call(`/pqkds-api/pqkds/nodes/${pkA}/keys/`, { token: session.token })
  check('★★ 节点令牌重签被拒（且说明是权限问题）', nodeReissue.code === 4000 && nodeReissue.msg.includes('仅管理员'),
    `msg=${nodeReissue.msg.slice(0, 60)}`)
  check('★★ 节点令牌删除被拒', nodeDelete.code === 4000 && nodeDelete.msg.includes('仅管理员'),
    `msg=${nodeDelete.msg.slice(0, 60)}`)
  check('★ 节点令牌看密钥被拒', nodeKeys.code === 4000 && nodeKeys.msg.includes('仅管理员'),
    `msg=${nodeKeys.msg.slice(0, 60)}`)
  check('★★ 三个拒绝里都**不含**「身份认证信息未提供」（闸门没接回断掉的链）',
    ![nodeReissue, nodeDelete, nodeKeys].some((r) => r.msg.includes(BROKEN_CHAIN_MSG)),
    '检查通过')

  // ===== 5. ★ 界面级：真点「重签凭证」与「删除」 =====
  console.log('\n== 5. ★ 界面级：在节点管理页真点这两个动作 ==')
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/nodegov/nodes` })
  await sleep(6000)
  const onPage = await ev(`location.pathname`)
  check('进入「节点管理」页', String(onPage).includes('nodes'), String(onPage))

  // ---- 5a. 重签凭证（界面）----
  const reissueClicked = await ev(`(() => {
    const rows=[...document.querySelectorAll('.el-table__row')]
    const row=rows.find(r=>r.innerText.includes(${JSON.stringify(NODE_A)}))
    if(!row) return 'NO_ROW'
    const b=[...row.querySelectorAll('button')].find(x=>/重签|凭证/.test(x.innerText))
    if(!b) return 'NO_BUTTON:'+[...row.querySelectorAll('button')].map(x=>x.innerText.trim()).join(',')
    b.click(); return 'CLICKED'
  })()`)
  check('该行有「重签凭证」入口并点了', reissueClicked === 'CLICKED', String(reissueClicked))
  await sleep(1200)
  // 确认框
  await ev(`(() => { const b=[...document.querySelectorAll('.el-message-box button')].find(x=>/签\\s*发|确定/.test(x.innerText)); if(b) b.click(); return true })()`)
  await sleep(6000)
  const reissueUi = await ev(`(() => {
    const el=document.querySelector('.el-dialog .code-text')
    const msgs=[...document.querySelectorAll('.el-message')].map(m=>m.innerText.trim())
    return { codeText: el ? el.innerText.trim() : '', masked: el ? el.classList.contains('is-masked') : null, msgs }
  })()`)
  check('★★ 界面点「重签凭证」成功弹出凭证弹窗（修复前这里只有红条「身份认证信息未提供」）',
    /^[•·*]{8,}$/.test(reissueUi?.codeText || '') && reissueUi?.masked === true,
    `code-text=${JSON.stringify((reissueUi?.codeText || '').slice(0, 16))} masked=${reissueUi?.masked} msgs=${JSON.stringify(reissueUi?.msgs || [])}`)
  check('★ 界面上没有「身份认证信息未提供」的报错',
    !(reissueUi?.msgs || []).some((m) => m.includes(BROKEN_CHAIN_MSG)),
    JSON.stringify(reissueUi?.msgs || []))
  await ev(`(() => { const b=[...document.querySelectorAll('.el-dialog__footer button')].find(x=>/我已保存/.test(x.innerText)); if(b) b.click(); return true })()`)
  await sleep(1500)

  // ---- 5b. 删除（界面）----
  const delClicked = await ev(`(() => {
    const rows=[...document.querySelectorAll('.el-table__row')]
    const row=rows.find(r=>r.innerText.includes(${JSON.stringify(NODE_A)}))
    if(!row) return 'NO_ROW'
    const b=[...row.querySelectorAll('button')].find(x=>x.innerText.trim()==='删除')
    if(!b) return 'NO_BUTTON'
    b.click(); return 'CLICKED'
  })()`)
  check('该行有「删除」入口并点了', delClicked === 'CLICKED', String(delClicked))
  await sleep(1500)
  await ev(`(() => { const b=[...document.querySelectorAll('.el-message-box button')].find(x=>/删\\s*除|确定/.test(x.innerText)); if(b) b.click(); return true })()`)
  await sleep(7000)
  const afterDelete = await ev(`(() => ({
    text: document.querySelector('.app-main')?.innerText || '',
    msgs: [...document.querySelectorAll('.el-message')].map(m=>m.innerText.trim())
  }))()`)
  check('★★ 界面删除成功（节点从列表消失）',
    !String(afterDelete?.text || '').includes(NODE_A),
    String(afterDelete?.text || '').includes(NODE_A) ? '仍在列表里' : '已消失')
  check('★ 删除没有报「身份认证信息未提供」',
    !(afterDelete?.msgs || []).some((m) => m.includes(BROKEN_CHAIN_MSG)),
    JSON.stringify(afterDelete?.msgs || []))

  // ===== 6. 对照：key-pool 闸门没被带坏 =====
  console.log('\n== 6. 对照：/key-pool/* 闸门不受影响 ==')
  const pool = await call('/pqkds-api/pqkds/key-pool/?page=1&limit=1', { token: adminToken })
  check('管理员读密钥池正常（改造没有误伤同套路的另一个命名空间）', pool.code === 2000,
    `code=${pool.code} msg=${pool.msg.slice(0, 40)}`)
  const poolAnon = await call('/pqkds-api/pqkds/key-pool/?page=1&limit=1')
  check('未登录读密钥池被拒（仍是 4000 + 未登录）', poolAnon.code === 4000 && poolAnon.msg.includes('未登录'),
    `msg=${poolAnon.msg.slice(0, 50)}`)

  // ===== 7. 已激活节点仍能免密登录（没有把节点侧一起挡掉） =====
  console.log('\n== 7. 反向护栏：节点侧登录不受影响 ==')
  const relogin = await lib.deviceLogin(`Node-GATE-N-${SEED}`)
  check('★ 节点仍能用设备凭据登录（闸门只收紧了管理员动作）', Boolean(relogin?.token),
    `令牌长度=${relogin?.token?.length || 0}`)

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.p)
  console.log(`总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  process.exitCode = failed.length ? 1 : 0
} catch (e) {
  console.error('\n[ERROR]', e.message)
  process.exitCode = 1
} finally {
  // 清理：删掉本脚本建的全部节点（A 可能已被界面删掉；B 已被接口删掉）
  try {
    const out = execFileSync('docker', ['exec', '-i', 'dvadmin3-django', 'python', '-'], {
      input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
ids = ['${NODE_A}', '${NODE_B}', 'Node-GATE-N-${SEED}']
rows = list(Node.objects.filter(node_id__in=ids))
deleted, _ = Node.objects.filter(pk__in=[n.pk for n in rows]).delete()
left = Node.objects.filter(node_id__in=ids).count()
print('nodes=%d deleted=%d left=%d' % (len(rows), deleted, left))
`,
      encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    }).trim()
    console.log(`  [info] 清理：${out}`)
  } catch (error) {
    console.log(`  [info] 清理失败：${String(error?.stderr || error?.message || error).slice(0, 200)}`)
  }
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}
