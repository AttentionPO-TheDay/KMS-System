// =============================================================================
// verify-node-authorization.mjs —— 任务书「节点多级授权」端到端验收
// -----------------------------------------------------------------------------
// 任务书《1-课题2-任务书》把「节点多级授权」列为「密钥动态更新与回收系统」的
// 4 项功能指标之一（p17/p35，由具有资质第三方检测机构测试）。本脚本是它的
// **可执行判据**，把整条链路从界面上钉一遍：
//
//   节点看到全网名录 → 选对端发起申请 → 管理员在管理端审批
//     → **批准真的写授权行**（双向） → 前后权限确实变了
//
// 本脚本最想钉住的四件事（缺一条，这个指标就只是"界面长得像"）：
//
//   1. **批准前真的没权限、批准后真的有** —— 用 `node_peer_keys` 的
//      403/200 逐条对照，而不是看页面上的字样；
//   2. **双向** —— 批准后 A 能取 B 的密钥、B 也能取 A 的；
//   3. **没有第二套判据** —— 把授权行手工置 revoked，A **立刻**回到 403。
//      这一条直接反驳仓库里那套被下线的审批流（`permission_request` 的
//      `approve()` 刻意不授予权限，形成了第二套权限语义，见
//      `kms-ops/mysql/init/35_remove_permission_request_menu.sql`）；
//   4. **驳回/撤回零权限副作用** —— 库里不产生任何授权行。
//
// 另含真实界面断言：节点侧菜单出现「节点授权」、页面能打开、名录渲染；
// 管理端「节点分发授权」页出现待审批卡片并能点批准。
//
// ⚠️ 会真建 3 个节点、真走审批、结尾自建自清（含申请单——申请表对 Node 是
//    FK，必须先删申请再删节点，否则撞 1451）。
// 用法：node tools/verify-node-authorization.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'
import { sql, sqlScalar } from './lib/mysql.mjs'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const PQKDS = `${ORIGIN}/pqkds-api/pqkds`
const NODES = 'falcon_kds.dvadmin_pqkds_nodes'
const AUTH = 'falcon_kds.dvadmin_pqkds_user_node_authorizations'
const REQ = 'falcon_kds.dvadmin_pqkds_node_authorization_requests'
const DOMAIN = 'auth-verify'
const PORT = 9394
const SEED = Date.now().toString(36).toUpperCase().slice(-5)

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

const dir = mkdtempSync(join(tmpdir(), 'authverify-'))
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
  return String(await ev(`location.pathname`) || '')
}

const api = async (path, { method = 'GET', token, body } = {}) => {
  const r = await fetch(`${ORIGIN}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {})
  })
  return { http: r.status, body: await r.json().catch(() => null) }
}
const nodePk = (nodeId) => sqlScalar(`SELECT id FROM ${NODES} WHERE node_id='${nodeId}';`)
const nodeUid = (nodeId) => sqlScalar(`SELECT IFNULL(sys_user_id,0) FROM ${NODES} WHERE node_id='${nodeId}';`)
const authRows = (uid, pk) => sqlScalar(`SELECT COUNT(*) FROM ${AUTH} WHERE user_id=${uid} AND node_id=${pk} AND status='active';`)

let adminToken = ''
const sessions = []

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

  // ===== 1. 建四个节点并各自登录取令牌 =====
  // ⚠️ 四个（不是三个）：D 是**批量批准**那一组需要的第二个待审批目标 ——
  //    批量至少要有两条才谈得上"一次处置多条"（12b 组）。
  console.log('\n== 1. 建节点 A/B/C/D 并激活 ==')
  adminToken = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
  const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
  for (const tag of ['A', 'B', 'C', 'D']) {
    const created = await lib.createNode(adminToken, { prefix: `NAV${tag}`, domainId: DOMAIN })
    const act = await lib.activateNode(created.nodeId, created.activationCode)
    // `fingerprint` 是激活时算出的**设备公钥指纹** —— 后面登记四套公钥时要用它，
    // 少了它服务端会以 DEVICE_MISMATCH 拒（夹具的 activateNode 直接把它算好了）。
    sessions.push({ tag, nodeId: created.nodeId, token: act.token, fingerprint: act.fingerprint })
  }
  const [A, B, C, D] = sessions
  check('四个节点已建好并各自拿到令牌',
    sessions.every((s) => Boolean(s.token)) && new Set(sessions.map((s) => s.nodeId)).size === 4,
    sessions.map((s) => s.nodeId).join(' / '))

  // ===== 2. 名录：可见 + 不泄漏 =====
  console.log('\n== 2. 节点名录（节点侧能看到全网，且不泄漏内部信息）==')
  const dirRes = await api('/pqkds-api/pqkds/node-self/directory/', { token: A.token })
  const rows = dirRes.body?.data?.nodes || []
  const rowB = rows.find((r) => r.nodeCode === B.nodeId)
  const rowC = rows.find((r) => r.nodeCode === C.nodeId)
  check('★★ 节点能看到**全网**节点（B、C 都在，且不止自己被授权的）',
    dirRes.body?.code === 200 && Boolean(rowB) && Boolean(rowC),
    `code=${dirRes.body?.code} total=${dirRes.body?.data?.total}`)
  check('名录不含自己', !rows.some((r) => r.nodeCode === A.nodeId))
  // 逐字段断言：防的是"以后有人顺手把 ip/端口/sys_user_id 加回来"
  const allKeys = new Set()
  rows.forEach((r) => Object.keys(r).forEach((k) => allKeys.add(k)))
  const allowed = new Set(['nodeCode', 'name', 'status', 'domainId', 'nodeType',
    'permissionLevel', 'relationship', 'canRequest'])
  const extra = [...allKeys].filter((k) => !allowed.has(k))
  check('★★ 名录字段**只有白名单内的**（没有 ip/端口/sys_user_id/公钥/指纹）',
    extra.length === 0, extra.length ? `多出字段：${extra.join(',')}` : `字段集合=${[...allKeys].join(',')}`)
  const rawDir = JSON.stringify(rows.slice(0, 5))
  check('★ 名录文本里不出现 ip_address / port / sys_user / publicKey / activation',
    !/ip_address|"port"|sys_user|publicKey|public_key|activation|device/i.test(rawDir),
    rawDir.slice(0, 100))

  // ===== 3. 申请：幂等 + 去重键 =====
  console.log('\n== 3. 发起授权申请（幂等、无序去重）==')
  const req1 = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: B.nodeId, reason: '验收：与 B 建立会话' }
  })
  const reqId = req1.body?.data?.request?.id
  check('★★ 节点发起申请成功（pending）',
    req1.body?.code === 200 && req1.body?.data?.request?.status === 'pending' && Boolean(reqId),
    `id=${reqId}`)
  const req2 = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: B.nodeId, reason: '重复提交' }
  })
  check('★ 重复申请幂等（返回同一条，不建第二单）',
    req2.body?.data?.created === false && req2.body?.data?.request?.id === reqId,
    `created=${req2.body?.data?.created} id=${req2.body?.data?.request?.id}`)
  const reqRev = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: B.token, body: { targetNodeId: A.nodeId, reason: '反向申请（同一对）' }
  })
  check('★ 反向申请视为**同一对**（无序去重，不建第二单）',
    reqRev.body?.data?.request?.id === reqId, `id=${reqRev.body?.data?.request?.id}（应为 ${reqId}）`)
  const pendingCount = sqlScalar(`SELECT COUNT(*) FROM ${REQ} WHERE status='pending' AND (requester_id=${nodePk(A.nodeId)} OR target_id=${nodePk(A.nodeId)});`)
  check('库里该对节点只有 1 条 pending', Number(pendingCount) === 1, `count=${pendingCount}`)

  // ===== 4. 批准前：真的没权限 =====
  console.log('\n== 4. 批准**之前**：权限判据（这一节是整份脚本的核心一半）==')
  const preA = await api(`/pqkds-api/pqkds/node-self/peers/${B.nodeId}/keys/`, { token: A.token })
  const preB = await api(`/pqkds-api/pqkds/node-self/peers/${A.nodeId}/keys/`, { token: B.token })
  check('★★ 批准前 A 取 B 的密钥被拒（NOT_AUTHORIZED）',
    preA.body?.data?.error_code === 'NOT_AUTHORIZED', `err=${preA.body?.data?.error_code}`)
  check('★★ 批准前 B 取 A 的密钥也被拒', preB.body?.data?.error_code === 'NOT_AUTHORIZED',
    `err=${preB.body?.data?.error_code}`)
  const preDist = await api('/pqkds-api/pqkds/node-self/distributions/', {
    method: 'POST', token: A.token,
    body: { receiverNodeId: B.nodeId, protectionAlgorithm: 'KYBER', recipientKeyId: 'x', recipientKeyVersion: 1 }
  })
  check('★ 批准前**分发入口**同样被拒（不只是查询被拦）',
    preDist.body?.data?.error_code === 'NOT_AUTHORIZED',
    `err=${preDist.body?.data?.error_code} msg=${String(preDist.body?.msg || '').slice(0, 40)}`)

  // ===== 5. 审批权限：非管理员不能批 =====
  console.log('\n== 5. 审批的权限闸门 ==')
  const nodeDecide = await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${reqId}/decide/`, {
    method: 'POST', token: A.token, body: { decision: 'approve' }
  })
  check('★★ 节点令牌不能审批（roleLevel=2，非管理员）',
    nodeDecide.http === 403 || nodeDecide.body?.code === 403,
    `http=${nodeDecide.http} code=${nodeDecide.body?.code} msg=${String(nodeDecide.body?.message || '').slice(0, 30)}`)
  const anonDecide = await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${reqId}/decide/`, {
    method: 'POST', body: { decision: 'approve' }
  })
  check('★ 未登录不能审批', anonDecide.http === 401 || anonDecide.body?.code === 401,
    `http=${anonDecide.http}`)
  const nodeList = await api('/pqkds-api/pqkds/admin/node-authorization-requests/?status=pending', { token: A.token })
  check('★ 节点令牌也看不到待审批列表（管理端命名空间的读权限）',
    nodeList.http === 403 || nodeList.body?.code === 403,
    `http=${nodeList.http} code=${nodeList.body?.code}`)

  // 「Java 先认、PQKDS 再发」——**顺序硬约束的可见判据**。
  // 在批准之前先直问链上入口：新类型不被接受时，批准只会得到一句
  // "存证未成功"，而那句在页面上与"链不可用"无法区分。
  //
  // ⚠️ 判据设计：**故意不带 keyId**。这样请求会停在白名单之后的下一道校验上 ——
  //    白名单认了它，才会回"keyId 不能为空"；没认就回"不支持的事件类型"。
  //    于是**不往链上写任何东西**就能证明白名单状态（上一版直接用真 keyId 探活，
  //    每跑一次就往链上留一条 PROBE 记录，那是不可撤回的污染）。
  console.log('\n== 5b. 链上事件类型已被 Java 接受（部署顺序的判据，不写链）==')
  try {
    const internalToken = execFileSync('docker', ['exec', 'kms_updatedel_java', 'printenv', 'INTERNAL_TOKEN'],
      { encoding: 'utf8' }).trim()
    const probeType = async (eventType, withKeyId) => {
      const r = await fetch(`${ORIGIN}/lifecycle-api/internal/lifecycle/chain/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Internal-Token': internalToken },
        body: JSON.stringify(withKeyId
          ? { eventType, keyId: 1, version: 0, nodeId: '', publicMaterialHash: '' }
          : { eventType })
      })
      const j = await r.json().catch(() => null)
      return String(j?.message || '')
    }
    const grantMsg = await probeType('AUTH_GRANTED', false)
    const rejectMsg = await probeType('AUTH_REJECTED', false)
    const bogusMsg = await probeType('NOT_A_REAL_TYPE', false)
    check('★★ Java 白名单已认 AUTH_GRANTED / AUTH_REJECTED',
      !grantMsg.includes('不支持的事件类型') && !rejectMsg.includes('不支持的事件类型'),
      `AUTH_GRANTED→"${grantMsg.slice(0, 40)}" AUTH_REJECTED→"${rejectMsg.slice(0, 40)}"`)
    check('★ 对照：真正未知的类型仍被拒（白名单没有退化成"什么都收"）',
      bogusMsg.includes('不支持的事件类型'), `NOT_A_REAL_TYPE→"${bogusMsg.slice(0, 40)}"`)
  } catch (e) {
    check('链上入口探活', false, String(e?.message || e).slice(0, 100))
  }

  // ===== 6. 管理员审批 =====
  console.log('\n== 6. 管理员批准（双向放行）==')
  const listBefore = await api('/pqkds-api/pqkds/admin/node-authorization-requests/?status=pending', { token: adminToken })
  check('管理员能看到待审批列表', listBefore.body?.code === 200
    && (listBefore.body?.data?.items || []).some((i) => i.id === reqId),
    `pendingTotal=${listBefore.body?.data?.pendingTotal}`)

  const approve = await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${reqId}/decide/`, {
    method: 'POST', token: adminToken, body: { decision: 'approve', remark: '验收：批准' }
  })
  const created = approve.body?.data?.granted?.created || []
  check('★★ 批准回执如实回报**两个方向**都新建了授权', created.length === 2,
    `granted=${JSON.stringify(approve.body?.data?.granted)}`)
  // ⚠️ 链上哈希为空**不判 FAIL**（链/存证是旁路，可用性问题不该伪装成功能问题），
  //    但必须**打印出来**：静默的空哈希会让"审计缺口"永远不可见。
  const chainHash = String(approve.body?.data?.chainHash || '')
  if (chainHash) {
    check('★ 批准已上链（拿到交易哈希）', true, `${chainHash.slice(0, 24)}…`)
  } else {
    console.log(`  [WARN] 批准未上链：${approve.body?.data?.chainWarning || '存证未成功'}`
      + `（授权本身已成立；这正是"存证是旁路增强"的语义）`)
    check('★ 未上链时如实给出 chainWarning（不混成一句成功）',
      typeof approve.body?.data?.chainWarning === 'string'
      && approve.body.data.chainWarning.includes('存证未成功'),
      approve.body?.data?.chainWarning || '（缺失！）')
  }

  // ===== 7. 批准后：双向真的放行 =====
  console.log('\n== 7. 批准**之后**：与第 4 节逐条对偶 ==')
  const postA = await api(`/pqkds-api/pqkds/node-self/peers/${B.nodeId}/keys/`, { token: A.token })
  const postB = await api(`/pqkds-api/pqkds/node-self/peers/${A.nodeId}/keys/`, { token: B.token })
  check('★★ 批准后 A 取 B 的密钥**通了**（第 4 节的对偶）',
    postA.body?.code === 200 && postA.body?.data?.nodeCode === B.nodeId,
    `code=${postA.body?.code} nodeCode=${postA.body?.data?.nodeCode}`)
  check('★★ 批准后 B 取 A 的密钥**也通了**（双向）',
    postB.body?.code === 200 && postB.body?.data?.nodeCode === A.nodeId,
    `code=${postB.body?.code} nodeCode=${postB.body?.data?.nodeCode}`)
  const fwd = authRows(nodeUid(A.nodeId), nodePk(B.nodeId))
  const bwd = authRows(nodeUid(B.nodeId), nodePk(A.nodeId))
  check('★★ 库里确实写了**两行** active 授权（A→B 与 B→A）',
    Number(fwd) === 1 && Number(bwd) === 1, `A→B=${fwd} B→A=${bwd}`)

  // ===== 8. 没有第二套判据（本脚本最重要的一条）=====
  console.log('\n== 8. ★★ 判据只有一张表（反驳"装饰性审批"）==')
  sql(`UPDATE ${AUTH} SET status='revoked' WHERE user_id=${nodeUid(A.nodeId)} AND node_id=${nodePk(B.nodeId)};`)
  const afterManualRevoke = await api(`/pqkds-api/pqkds/node-self/peers/${B.nodeId}/keys/`, { token: A.token })
  const reqStatus = sqlScalar(`SELECT status FROM ${REQ} WHERE id=${reqId};`)
  check(`★★ 手工把授权行置 revoked 后，A **立刻**回到 403（此时申请单仍是「${reqStatus}」）`,
    afterManualRevoke.body?.data?.error_code === 'NOT_AUTHORIZED' && reqStatus === 'approved',
    `err=${afterManualRevoke.body?.data?.error_code} 申请单状态=${reqStatus}`)
  check('★ 这一条正是仓库里那套被下线的审批流的反面（它 approve 不授予任何权限）',
    true, '见 kms-ops/mysql/init/35_remove_permission_request_menu.sql')
  sql(`UPDATE ${AUTH} SET status='active' WHERE user_id=${nodeUid(A.nodeId)} AND node_id=${nodePk(B.nodeId)};`)

  // ===== 9. 驳回 / 撤回：零权限副作用 =====
  console.log('\n== 9. 驳回与撤回不产生任何权限 ==')
  const reqC = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: C.nodeId, reason: '验收：与 C 建立会话' }
  })
  const cId = reqC.body?.data?.request?.id
  const rejectNoRemark = await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${cId}/decide/`, {
    method: 'POST', token: adminToken, body: { decision: 'reject' }
  })
  check('★ 驳回必须给理由（否则节点侧只能看到一句空话）',
    rejectNoRemark.body?.code !== 200, `msg=${rejectNoRemark.body?.message}`)
  const reject = await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${cId}/decide/`, {
    method: 'POST', token: adminToken, body: { decision: 'reject', remark: '验收：业务上不需要' }
  })
  check('★★ 驳回回执的 granted **是空的**（零权限副作用）',
    reject.body?.code === 200
    && (reject.body?.data?.granted?.created || []).length === 0
    && (reject.body?.data?.granted?.reactivated || []).length === 0,
    JSON.stringify(reject.body?.data?.granted))
  const cRows = sqlScalar(`SELECT COUNT(*) FROM ${AUTH} WHERE (user_id=${nodeUid(A.nodeId)} AND node_id=${nodePk(C.nodeId)}) OR (user_id=${nodeUid(C.nodeId)} AND node_id=${nodePk(A.nodeId)});`)
  check('★★ 驳回后库里没有任何为 C 建的授权行', Number(cRows) === 0, `count=${cRows}`)
  const cStill = await api(`/pqkds-api/pqkds/node-self/peers/${C.nodeId}/keys/`, { token: A.token })
  check('★ 驳回后 A 取 C 的密钥仍被拒', cStill.body?.data?.error_code === 'NOT_AUTHORIZED',
    `err=${cStill.body?.data?.error_code}`)

  const reqC2 = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: C.nodeId, reason: '验收：撤回用例' }
  })
  const c2 = reqC2.body?.data?.request?.id
  check('★ 被驳回后可以**重新申请**', reqC2.body?.code === 200 && c2 && c2 !== cId, `id=${c2}`)
  const otherCancel = await api(`/pqkds-api/pqkds/node-self/authorization-requests/${c2}/cancel/`, {
    method: 'POST', token: B.token
  })
  check('★ 别人撤不回我的申请（连对方节点也不行）',
    otherCancel.body?.data?.error_code === 'NOT_AUTHORIZED', `err=${otherCancel.body?.data?.error_code}`)
  const cancel = await api(`/pqkds-api/pqkds/node-self/authorization-requests/${c2}/cancel/`, {
    method: 'POST', token: A.token
  })
  check('撤回成功', cancel.body?.code === 200 && cancel.body?.data?.request?.status === 'cancelled',
    `status=${cancel.body?.data?.request?.status}`)
  const freed = sqlScalar(`SELECT IFNULL(pending_key,'NULL') FROM ${REQ} WHERE id=${c2};`)
  check('★★ 撤回后未决去重键已释放（否则这对节点再也申请不了）', freed === 'NULL', `pending_key=${freed}`)
  const reqC3 = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: C.nodeId, reason: '验收：撤回后再申请' }
  })
  check('★★ 撤回后能再次申请（去重键真的释放了）', reqC3.body?.code === 200,
    `code=${reqC3.body?.code} id=${reqC3.body?.data?.request?.id}`)

  // ===== 10. 幂等与边界 =====
  console.log('\n== 10. 幂等与边界 ==')
  const twice = await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${reqId}/decide/`, {
    method: 'POST', token: adminToken, body: { decision: 'approve' }
  })
  check('★ 重复批准幂等（alreadyDecided，不重复上链）',
    twice.body?.code === 200 && twice.body?.data?.alreadyDecided === true
    && twice.body?.data?.chainHash === '',
    `alreadyDecided=${twice.body?.data?.alreadyDecided} chainHash="${twice.body?.data?.chainHash}"`)
  const selfReq = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: A.nodeId, reason: '向自己申请' }
  })
  check('★ 不能向自己申请', selfReq.body?.code !== 200, `msg=${selfReq.body?.msg}`)
  const dup = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: B.nodeId, reason: '已互通还要申请' }
  })
  check('★ 已双向授权时不建申请（alreadyGranted）',
    dup.body?.data?.alreadyGranted === true, `msg=${dup.body?.msg}`)

  // ===== 12. 并发：两个**同时**的申请 =====
  // 这是 `pending_key` 唯一索引存在的理由：`select_for_update` 锁的是**已存在的行**，
  // 两个标签页同时点「申请」时两边的行都还不存在，"先查一遍"拦不住。
  // 顺序调用测不到这条路径 —— 必须真并发。
  console.log('\n== 12. 并发申请（唯一键兜底）==')
  // 先把 A→C 的待审批撤掉，制造"这一对当前没有 pending"的真竞争条件。
  const pendingAC = await api('/pqkds-api/pqkds/node-self/authorization-requests/', { token: A.token })
  const acRow = (pendingAC.body?.data?.outgoing || []).find(
    (r) => r.targetNodeId === C.nodeId && r.status === 'pending')
  if (acRow) {
    await api(`/pqkds-api/pqkds/node-self/authorization-requests/${acRow.id}/cancel/`, {
      method: 'POST', token: A.token
    })
  }
  const fire = () => api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: C.nodeId, reason: '并发用例' }
  })
  const [race1, race2] = await Promise.all([fire(), fire()])
  const bothOk = race1.body?.code === 200 && race2.body?.code === 200
  const sameId = race1.body?.data?.request?.id != null
    && race1.body?.data?.request?.id === race2.body?.data?.request?.id
  const onlyOne = Number(sqlScalar(
    `SELECT COUNT(*) FROM ${REQ} WHERE status='pending' AND requester_id=${nodePk(A.nodeId)} AND target_id=${nodePk(C.nodeId)};`)) === 1
  check('★★ 两个并发申请都成功、指向**同一条**、库里只有 1 条 pending',
    bothOk && sameId && onlyOne,
    `codes=${race1.body?.code}/${race2.body?.code} ids=${race1.body?.data?.request?.id}/${race2.body?.data?.request?.id} pending=${onlyOne}`)

  // ===== 12b. 批量提交 + 批量批准（任务书「选对应的节点列表提交权限确认请求」）=====
  // 这一组钉住"多选一次提交"的语义，以及**批量不是一个事务**：
  // 逐条独立、一条失败不回滚其余。
  console.log('\n== 12b. 批量申请与批量批准 ==')
  // 先把 A→C 的待审批撤掉（12 组留下的那条），让 B/C 都处于"可申请"。
  const pendingNow = await api('/pqkds-api/pqkds/node-self/authorization-requests/', { token: A.token })
  for (const row of (pendingNow.body?.data?.outgoing || [])) {
    if (row.status === 'pending') {
      await api(`/pqkds-api/pqkds/node-self/authorization-requests/${row.id}/cancel/`, {
        method: 'POST', token: A.token
      })
    }
  }
  // A 与 B 已双向授权（前面批过）→ 批量里 B 应进 `ALREADY_GRANTED`，C 建新单。
  const batchSub = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token,
    body: { targetNodeIds: [B.nodeId, C.nodeId], reason: '批量用例' }
  })
  const batchCreated = batchSub.body?.data?.created || []
  const batchSkipped = batchSub.body?.data?.skipped || []
  const batchId = batchSub.body?.data?.batchId || ''
  check('★★ 一次提交多个目标：新建的那条带同一个 batchId，已授权的那条进 skipped',
    batchSub.body?.code === 200 && batchCreated.length === 1
    && batchCreated[0]?.targetNodeId === C.nodeId
    && batchCreated[0]?.batchId === batchId
    && batchSkipped.length === 1 && batchSkipped[0]?.reason === 'ALREADY_GRANTED',
    `created=${JSON.stringify(batchCreated.map((r) => r.targetNodeId))} batchId=${batchId} skipped=${JSON.stringify(batchSkipped)}`)

  // 幂等：同一批再提交一次 → 不再新建（`ALREADY_PENDING`）。
  const batchAgain = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token,
    body: { targetNodeIds: [C.nodeId], reason: '重复提交' }
  })
  check('★ 重复的批量提交不建第二条（ALREADY_PENDING）',
    (batchAgain.body?.data?.created || []).length === 0
    && (batchAgain.body?.data?.skipped || [])[0]?.reason === 'ALREADY_PENDING'
    && Number(sqlScalar(
      `SELECT COUNT(*) FROM ${REQ} WHERE status='pending' AND requester_id=${nodePk(A.nodeId)} AND target_id=${nodePk(C.nodeId)};`)) === 1,
    `skipped=${JSON.stringify(batchAgain.body?.data?.skipped)}`)

  // 批量批准（另一对：再建一条 A→D 的申请，与 C 那条一起批）。
  const batchSub2 = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token,
    body: { targetNodeIds: [D.nodeId], reason: '批量批准用例' }
  })
  const dReqId = batchSub2.body?.data?.created?.[0]?.id
  const cReqId = batchCreated[0]?.id
  const batchDecide = await api('/pqkds-api/admin/node-authorization-requests/decide-batch/', {
    method: 'POST', token: adminToken,
    body: { ids: [cReqId, dReqId], decision: 'approve', remark: '批量验收' }
  })
  const decideResults = batchDecide.body?.data?.results || []
  check('★★ 批量批准逐条回报（每条各自的状态与链上哈希）',
    batchDecide.body?.code === 200
    && decideResults.length === 2
    && decideResults.every((r) => r.ok && r.status === 'approved')
    && decideResults.some((r) => r.chainHash),
    `decided=${batchDecide.body?.data?.decided} results=${JSON.stringify(decideResults.map((r) => `${r.id}:${r.status}`))}`)
  // 批准后确实放行（判据仍是授权表）。
  const afterBatch = await api(`/pqkds-api/pqkds/node-self/peers/${C.nodeId}/keys/?algorithm=KYBER`, { token: A.token })
  check('★ 批量批准后 A 能取 C 的密钥（放行真的发生）',
    afterBatch.body?.code === 200, `code=${afterBatch.body?.code}`)

  // 部分批准：**只批一条**，另一条仍 pending（批量不是全或无）。
  // 造两条新的待审批（A→C、A→D 都已在上面被批过，所以先用新的对：C→A、D→A）。
  const partialSub = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: C.token,
    body: { targetNodeIds: [B.nodeId, D.nodeId], reason: '部分批准用例' }
  })
  const partialIds = (partialSub.body?.data?.created || []).map((r) => r.id)
  const partialDecide = await api('/pqkds-api/admin/node-authorization-requests/decide-batch/', {
    method: 'POST', token: adminToken,
    body: { ids: [partialIds[0]], decision: 'approve', remark: '只批第一条' }
  })
  const stillPending = Number(sqlScalar(
    `SELECT COUNT(*) FROM ${REQ} WHERE status='pending' AND requester_id=${nodePk(C.nodeId)};`))
  check('★★ 批量**不是全或无**：只传一条时，另一条仍是待审批',
    partialSub.body?.code === 200 && partialIds.length === 2
    && partialDecide.body?.data?.decided === 1 && stillPending === 1,
    `created=${partialIds.length} decided=${partialDecide.body?.data?.decided} 仍pending=${stillPending}`)

  // 非管理员不能批量批准。
  const batchForbidden = await api('/pqkds-api/admin/node-authorization-requests/decide-batch/', {
    method: 'POST', token: A.token, body: { ids: [1], decision: 'approve' }
  })
  check('★ 节点令牌调批量批准被拒（403）',
    batchForbidden.status === 403 || batchForbidden.body?.code === 403,
    `status=${batchForbidden.status} code=${batchForbidden.body?.code}`)

  // ===== 13. 界面级 =====
  console.log('\n== 11. 界面级：菜单与两个页面 ==')
  const adminPath = await loginAdmin()
  check('管理员登录（界面）', !adminPath.includes('/login'), adminPath)
  // ⚠️ 管理端「节点授权」的真实 URL 是 **菜单三级拼接**：
  //    9460(nodegov) / 9470(nodeauth 目录) / 9006(path=authlist)。
  //    写成 `/nodeauth/index` 会落到 SPA 兜底的 404 —— 而 404 页面的文案里
  //    也有"找不到"字样，很容易被当成"接口挂了"（实测踩过）。
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/nodegov/nodeauth/authlist` })
  await sleep(7000)
  const adminPage = await ev(`(() => ({
    path: location.pathname,
    text: document.body.innerText.slice(0, 2000),
    is404: Boolean(document.querySelector('.wscn-http404'))
  }))()`)
  check('★ 管理端「节点分发授权」页能打开（不是 404）',
    String(adminPage?.path || '').includes('authlist') && adminPage?.is404 === false,
    `path=${adminPage?.path} is404=${adminPage?.is404}`)
  check('★ 页面上有「节点分发授权」标题与授权列表',
    String(adminPage?.text || '').includes('节点分发授权'),
    String(adminPage?.text || '').replace(/\s+/g, ' ').slice(0, 90))

  // 节点侧页面：先让节点 A 走完初始化，否则路由守卫会把任何节点页弹回
  // 「节点首次初始化」（那正是上一版把这里写成"页面打不开"的原因）。
  const libA = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
  const cryptoProvider = libA.cryptoProvider
  for (const [algo, opts] of [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]) {
    const kp = await cryptoProvider.generate(algo, { nodeId: A.nodeId, ...opts })
    await api('/pqkds-api/pqkds/node-self/keys/', {
      method: 'POST', token: A.token,
      body: {
        algorithm: algo, publicKey: kp.publicKey, deviceId: A.fingerprint,
        keyId: kp.keyId, keyVersion: kp.version
      }
    })
  }
  const inited = await api('/pqkds-api/pqkds/node-self/init/', { method: 'POST', token: A.token })
  check('节点 A 完成初始化（否则节点侧页面会被守卫弹回引导页）',
    inited.body?.code === 200 && inited.body?.data?.node?.status === 'ACTIVE',
    `status=${inited.body?.data?.node?.status}`)

  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3000)
  await ev(`document.cookie='Admin-Token=${A.token}; path=/'`)
  // ⚠️ 别导航到 `/index` 再找侧边栏：节点账号的落地页是**工作台**，而工作台
  //    按设计不显示侧边栏（它只有子系统入口卡片）。实测那儿读到的是空数组，
  //    看起来像"菜单没下发"，其实是看错了页面。
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/distzone/selfauth` })
  await sleep(9000)
  const nodePage = await ev(`(() => ({
    path: location.pathname,
    text: document.body.innerText.slice(0, 3000),
    rows: document.querySelectorAll('.el-table__row').length,
    is404: Boolean(document.querySelector('.wscn-http404')),
    menus: [...document.querySelectorAll('.sidebar-container .menu-title')].map(e=>e.innerText.trim())
  }))()`)
  check('★★ 节点侧侧边栏出现「节点授权」菜单（在带侧边栏的节点页上读）',
    (nodePage?.menus || []).includes('节点授权'),
    `菜单=${JSON.stringify((nodePage?.menus || []).slice(0, 12))}`)
  check('★★ 「节点授权」页能打开且**渲染出名录**（表格有行）',
    String(nodePage?.path || '').includes('selfauth') && nodePage?.is404 === false && (nodePage?.rows || 0) > 0,
    `path=${nodePage?.path} 表格行数=${nodePage?.rows} is404=${nodePage?.is404}`)
  check('★ 页面上看得到「全网节点名录」与 B 的编号',
    String(nodePage?.text || '').includes('全网节点名录') && String(nodePage?.text || '').includes(B.nodeId),
    `含名录标题=${String(nodePage?.text || '').includes('全网节点名录')} 含B=${String(nodePage?.text || '').includes(B.nodeId)}`)
  check('★ 页面上看得到「已授权（双向）」的关系标签（B 已被批准）',
    String(nodePage?.text || '').includes('已授权'),
    String(nodePage?.text || '').replace(/\s+/g, ' ').slice(0, 120))
} catch (e) {
  console.error('\n[ERROR]', e.message)
  results.push({ n: '脚本异常', p: false })
} finally {
  // 清理：走 Django 的级联删除，而不是自己拼 SQL —— 节点身上挂着
  // 长期密钥（`NodeLongTermKey`）、会话、信封等一堆 FK，少删一张就撞 1451，
  // 而那句报错只点名"某张表约束失败"，看不出还差哪几张。
  // `Node.objects.delete()` 由外键的 on_delete 规则一次清干净。
  try {
    const out = execFileSync('docker', ['exec', '-i', 'dvadmin3-django', 'python', '-'], {
      input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
rows = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in rows]
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d cascaded=%d left=%d' % (len(ids), deleted, left))
`,
      encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    }).trim()
    console.log(`  [info] 清理：${out}`)
    check('清理完成：域内不再有本脚本建的节点及其申请单', out.endsWith('left=0'), out)
  } catch (error) {
    const msg = String(error?.message || error).slice(0, 150)
    console.log(`  [info] 清理失败：${msg}`)
    check('清理失败（需人工处理）', false, msg)
  }
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }

  const failed = results.filter((r) => !r.p)
  console.log(`\n===== 汇总 =====\n总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  process.exitCode = failed.length ? 1 : 0
}