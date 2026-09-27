#!/usr/bin/env node
import { captchaFields } from './lib/captcha.mjs'
/**
 * P1 验收脚本（纯 HTTP，无浏览器依赖）
 * =============================================================================
 * 覆盖重构计划 P1 的五项改动，每项都以「可观测的行为」为断言，而不是看代码：
 *
 *   P1-1  D1：PUBLIC_KEY_LIST 全链路删除
 *         → /generate-api/generate/key/public-list 必须不存在（404）
 *         → /generate-api/permission/request/* 必须不存在（404）
 *   P1-2  D2：权限管理页删除，申请入口迁到「更新与回收」页
 *         → 用户前台不再有 /permissions 路由（前端断言由 UI 扫描脚本负责）
 *   P1-3  Q8/D14：我的操作日志
 *         → /lifecycle-api/lifecycle/my-logs/{key-operations,operations,logins} 可用
 *         → 且**越权注入 userId / operName / userName 必须被服务端忽略**
 *   P1-4  D9：登录后按 roleLevel 分流（前端断言由 UI 扫描脚本负责）
 *   P1-5  D-原文：管理端菜单删「密钥生成」
 *         → /lifecycle-api/getRouters 里不得出现「密钥生成」
 *
 * 用法：node tools/verify-p1.mjs [origin]
 * =============================================================================
 */

const ORIGIN = process.argv[2] || 'http://127.0.0.1'

let pass = 0
let fail = 0
const failures = []

function check(name, ok, detail = '') {
  if (ok) {
    pass++
    console.log(`  [OK]   ${name}${detail ? '  ' + detail : ''}`)
  } else {
    fail++
    failures.push(name)
    console.log(`  [FAIL] ${name}${detail ? '  ' + detail : ''}`)
  }
}

async function api(base, path, { token, method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${ORIGIN}${base}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  })
  const text = await res.text()
  let json = null
  try {
    json = JSON.parse(text)
  } catch {
    /* 非 JSON（例如 SPA 回落的 HTML）—— 保留 null，由调用方按 status 判断 */
  }
  return { status: res.status, json, text }
}

async function login(username, password) {
  const res = await api('/lifecycle-api', '/login', { method: 'POST', body: { username, password, ...(await captchaFields(ORIGIN)) } })
  const token = res.json?.token
  if (!token) {
    throw new Error(`登录失败 ${username}: HTTP ${res.status} ${res.text.slice(0, 200)}`)
  }
  return token
}

function menuNames(routers) {
  const out = []
  const walk = (nodes) => {
    for (const n of nodes || []) {
      const title = n.meta?.title
      if (title) out.push(title)
      walk(n.children)
    }
  }
  walk(routers)
  return out
}

console.log(`\n=== P1 验收 @ ${ORIGIN} ===\n`)

// ---------------------------------------------------------------------------
// 准备：三个身份
//   admin            role_level=0  管理员（超管）
//   yx               role_level=2  普通用户
//   test             role_level=0  另一个管理员（用于验证用户名严格相等）
// 口令均为 admin123（与库中 BCrypt 哈希一致）
// ---------------------------------------------------------------------------
const adminToken = await login('admin', 'admin123')
const userToken = await login('yx', 'admin123')
const admin2Token = await login('test', 'admin123')
console.log(`  登录成功：admin / yx / test（token 长度 ${adminToken.length} / ${userToken.length} / ${admin2Token.length}）\n`)

// ---------------------------------------------------------------------------
// P1-5：管理端菜单不得再有「密钥生成」
// ---------------------------------------------------------------------------
console.log('P1-5 管理端菜单删「密钥生成」')
{
  const res = await api('/lifecycle-api', '/getRouters', { token: adminToken })
  check('GET /getRouters 返回 200', res.status === 200, `HTTP ${res.status}`)
  const names = menuNames(res.json?.data)
  check('菜单不含「密钥生成」', !names.includes('密钥生成'))
  // 反向断言：防止"把整个密钥管理组删掉"这种过度删除
  check('菜单仍含「密钥更新」', names.includes('密钥更新'))
  check('菜单仍含「密钥回收」', names.includes('密钥回收'))
  check('菜单仍含「用户密钥池」', names.includes('用户密钥池'))
  console.log(`         当前菜单(${names.length})：${names.join(' / ')}`)
}

// ---------------------------------------------------------------------------
// P1-1：PUBLIC_KEY_LIST 后端接口必须消失
// ---------------------------------------------------------------------------
// 注意 RuoYi 的响应约定：它把很多错误也放在 HTTP 200 里，靠 body 的 `code` 表达
// （未认证 = HTTP 200 + {"code":401}）。所以这里不能只看 HTTP 状态码，
// 必须同时看 body。真正"没有这条路由"的情况才是 HTTP 404。
console.log('\nP1-1 D1：PUBLIC_KEY_LIST 全链路删除')
{
  // 生成域整套权限子系统已删除 → 这两条路由必须彻底不存在
  const permList = await api('/generate-api', '/permission/request/list', { token: userToken })
  check('GET /generate-api/permission/request/list 路由已不存在',
    permList.status === 404, `HTTP ${permList.status} ${permList.text.slice(0, 80)}`)

  const permSubmit = await api('/generate-api', '/permission/request/submit', {
    token: userToken,
    method: 'POST',
    body: { userId: 101, requestReason: '验证删除' }
  })
  check('POST /generate-api/permission/request/submit 路由已不存在',
    permSubmit.status === 404, `HTTP ${permSubmit.status} ${permSubmit.text.slice(0, 80)}`)

  // public-list 删除后，该路径会被 `GET /generate/key/{keyId}` 捕获，
  // 于是报"参数 keyId 类型不匹配"。判定标准是：**绝不能返回密钥列表**。
  const pub = await api('/generate-api', '/generate/key/public-list', { token: userToken })
  const leakedRows = Array.isArray(pub.json?.rows) ? pub.json.rows : []
  check('GET /generate/key/public-list 不再返回任何密钥列表',
    pub.json?.code !== 200 && leakedRows.length === 0,
    `HTTP ${pub.status} code=${pub.json?.code} rows=${leakedRows.length}`)

  // 生成域仅剩「查自己的密钥」这一个列表接口，且必须仍可用
  const own = await api('/generate-api', '/generate/key/list', { token: userToken })
  check('GET /generate/key/list 仍可用', own.json?.code === 200 && Array.isArray(own.json?.rows),
    `HTTP ${own.status} code=${own.json?.code}`)
}

// ---------------------------------------------------------------------------
// P1-3：我的操作日志三接口 + 服务端强制按令牌过滤
// ---------------------------------------------------------------------------
console.log('\nP1-3 Q8/D14：我的操作日志（服务端按令牌强制过滤）')
{
  const endpoints = [
    ['/lifecycle/my-logs/key-operations', 'key-operations'],
    ['/lifecycle/my-logs/operations', 'operations'],
    ['/lifecycle/my-logs/logins', 'logins']
  ]

  for (const [path] of endpoints) {
    const res = await api('/lifecycle-api', path, { token: userToken })
    const okShape = res.json?.code === 200 && Array.isArray(res.json?.rows)
    check(`GET ${path} 返回分页结构`, okShape, `HTTP ${res.status} code=${res.json?.code} rows=${res.json?.rows?.length}`)

    // RuoYi 把"未认证"也放在 HTTP 200 里，用 body.code = 401 表达
    const anon = await api('/lifecycle-api', path)
    check(`${path} 未带令牌必须被拒`, anon.json?.code === 401,
      `HTTP ${anon.status} code=${anon.json?.code}`)
  }

  // 越权注入：普通用户把 userId/operName/userName 塞进查询串，服务端必须忽略这些值
  const injectKey = await api('/lifecycle-api', '/lifecycle/my-logs/key-operations?userId=1&userName=admin', {
    token: userToken
  })
  const leakedKeyRows = (injectKey.json?.rows || []).filter(
    (r) => String(r.userId) === '1' || r.userName === 'admin'
  )
  check('注入 userId/userName 后仍看不到 admin 的密钥操作记录', leakedKeyRows.length === 0,
    `越权行数=${leakedKeyRows.length}`)

  const injectOper = await api('/lifecycle-api', '/lifecycle/my-logs/operations?operName=admin', {
    token: userToken
  })
  const leakedOperRows = (injectOper.json?.rows || []).filter((r) => r.operName && r.operName !== 'yx')
  check('注入 operName=admin 后仍只返回自己的操作日志', leakedOperRows.length === 0,
    `越权行数=${leakedOperRows.length}`)

  const injectLogin = await api('/lifecycle-api', '/lifecycle/my-logs/logins?userName=admin', {
    token: userToken
  })
  const leakedLoginRows = (injectLogin.json?.rows || []).filter((r) => r.userName && r.userName !== 'yx')
  check('注入 userName=admin 后仍只返回自己的登录日志', leakedLoginRows.length === 0,
    `越权行数=${leakedLoginRows.length}`)

  // ---- 服务端强制过滤：普通用户不得看到系统账号的操作日志 ----
  // sys_oper_log 里现有 41 行，oper_name 全是 System-Kafka / System-ChainConsumer
  // （Kafka 消费者与链上消费者写入的），没有任何真实用户的记录。
  // 一个"没加过滤条件"的接口会把它们全返回；yx 必须一行都看不到。
  const yxOper = await api('/lifecycle-api', '/lifecycle/my-logs/operations?pageSize=200', {
    token: userToken
  })
  const systemRows = (yxOper.json?.rows || []).filter((r) => /^System-/.test(r.operName || ''))
  check('普通用户看不到 System-* 的系统操作日志', systemRows.length === 0,
    `越权行数=${systemRows.length}，本用户可见 ${yxOper.json?.rows?.length} 行`)

  // ---- 用户名必须严格相等，而不是 LIKE ----
  // 这是真实存在的数据碰撞：库中 test 有 1 条登录日志、test01 有 13 条。
  // 底层 XML 原来是 `user_name like concat('%', #{userName}, '%')`，
  // 若按它过滤，test 会连 test01 的 13 条一起读到。
  const testLogins = await api('/lifecycle-api', '/lifecycle/my-logs/logins?pageSize=200', {
    token: admin2Token
  })
  const rows = testLogins.json?.rows || []
  const foreign = rows.filter((r) => r.userName !== 'test')
  check('用户名严格相等：test 读不到 test01 的登录日志', foreign.length === 0,
    `误命中 ${foreign.length} 行（若用 LIKE 会命中 test01 的 13 行）；本用户可见 ${rows.length} 行`)
  check('test 自己的登录日志确实能读到（证明上面的 0 不是"接口坏了"）', rows.length > 0,
    `rows=${rows.length}`)

  // 主动制造一条 adminzz 的失败登录，验证 admin 同样不会读到它
  for (let i = 0; i < 2; i++) {
    await api('/lifecycle-api', '/login', {
      method: 'POST',
      body: { username: 'adminzz', password: 'definitely-wrong-password', ...(await captchaFields(ORIGIN)) }
    })
  }
  await new Promise((r) => setTimeout(r, 1500)) // 登录日志是异步落库的（AsyncManager）

  const adminLogins = await api('/lifecycle-api', '/lifecycle/my-logs/logins?pageSize=200', {
    token: adminToken
  })
  const bleed = (adminLogins.json?.rows || []).filter((r) => r.userName === 'adminzz')
  check('admin 不会读到 adminzz 的登录日志', bleed.length === 0, `误命中行数=${bleed.length}`)
}

// ---------------------------------------------------------------------------
// 附加：普通用户不得进入管理端的服务端侧前提（D9 的兜底）
// ---------------------------------------------------------------------------
console.log('\n附加：D9 分流的数据前提')
{
  const info = await api('/lifecycle-api', '/getInfo', { token: userToken })
  check('普通用户 roleLevel = 2（>0，不应进管理端）', Number(info.json?.user?.roleLevel) === 2,
    `roleLevel=${info.json?.user?.roleLevel}`)

  const adminInfo = await api('/lifecycle-api', '/getInfo', { token: adminToken })
  check('管理员 roleLevel = 0（<=0，应进管理端）', Number(adminInfo.json?.user?.roleLevel) === 0,
    `roleLevel=${adminInfo.json?.user?.roleLevel}`)
}

// ---------------------------------------------------------------------------
// P1-2 / D2：权限申请入口迁移后的端到端流程，以及一条关键的权限不变量
// ---------------------------------------------------------------------------
// 这条断言守的是一个真实缺陷：临时权限审批流原本会改写申请人的 role_level
// （审批通过 → requestLevel，本域固定为 0；回退 → 2，或"还有其它已通过申请"时 → 1）。
// 在 D9 之后这是硬伤：登录分流判据正是 role_level <= 0，
// 于是一个普通用户被批准「自动更新」临时权限后，下次登录会被直接送进管理控制台；
// 而回退写 1 又会凭空造出已废弃的「中级用户」等级。
//
// 正确的语义是：**临时权限只由 permission_request 表判定，role_level 是纯静态属性。**
console.log('\nP1-2 / D2：权限申请端到端 + role_level 不变量')
{
  const TEST_KEY_NAME = 'verify-p1-D2-临时测试密钥'
  const VALID_UA = '04b038bd3450aff1c985e74918f6aeac37a6c05193c9c68654ab02dad094279177e8d692af475613983366ea67abc310e75b3c1fbe1ae51d4dda1519762f8e1b2e'

  const roleLevelOf = async (token) => {
    const r = await api('/lifecycle-api', '/getInfo', { token })
    return Number(r.json?.user?.roleLevel)
  }
  // 服务端拒绝时 body.code 是 500（RuoYi 约定），这里连消息一起断言，
  // 避免"因为别的原因报 500"被误判成"权限被正确拦截"。
  const isDeniedWith = (res, keyword) =>
    res.json?.code === 500 && String(res.json?.msg || '').includes(keyword)

  // ---- 准备一把 yx 自己的密钥（幂等：已存在就复用）----
  // 注意字段名是 `uA`（Java 侧 getter 为 getuA，Jackson 序列化成 uA）；
  // 写成小写 `ua` 会被 Go 侧判为"必填参数缺失(UA)"。
  let keyId = null
  const findKey = async () => {
    const r = await api('/generate-api', '/generate/key/list?pageSize=100', { token: userToken })
    const hit = (r.json?.rows || []).find((k) => k.keyName === TEST_KEY_NAME)
    return hit ? hit.keyId : null
  }
  keyId = await findKey()
  let createMsg = ''
  if (!keyId) {
    const created = await api('/generate-api', '/generate/keymanage', {
      token: userToken,
      method: 'POST',
      body: {
        encrytType: '无证书非对称加密',
        encrytName: 'SM2',
        keyName: TEST_KEY_NAME,
        keyUse: '自动化验收',
        keyDomain: 'A',
        uA: VALID_UA
      }
    })
    createMsg = created.json?.msg || ''
    // 落库走 Kafka，异步；轮询等待
    for (let i = 0; i < 20 && !keyId; i++) {
      await new Promise((r) => setTimeout(r, 700))
      keyId = await findKey()
    }
  }
  check('能为 yx 准备一把测试密钥（后续断言的前提）', Boolean(keyId),
    `keyId=${keyId}${createMsg ? ' createMsg=' + createMsg : ''}`)

  const tryAutoUpdate = async (value) =>
    api('/lifecycle-api', '/lifecycle/keymanage/auto-update', {
      token: userToken,
      method: 'PUT',
      body: { keyId, autoUpdate: value }
    })

  const levelBefore = await roleLevelOf(userToken)
  check('起始状态：yx 是普通用户（role_level = 2）', levelBefore === 2, `role_level=${levelBefore}`)

  // ---- 授权前：必须因为"没有自动更新权限"被拒（不是别的理由）----
  if (keyId) {
    const beforeGrant = await tryAutoUpdate('1')
    check('授权前无法修改自动更新（且拒绝理由就是权限不足）',
      isDeniedWith(beforeGrant, '没有自动更新操作权限'),
      `code=${beforeGrant.json?.code} msg=${beforeGrant.json?.msg}`)
  }

  // ---- yx 提交申请 ----
  // requestLevel 由服务端固定为 0，这里刻意**不传**，以固定"客户端不传也能成功"这一修复。
  const submit = await api('/lifecycle-api', '/permission/request/submit', {
    token: userToken,
    method: 'POST',
    body: { requestReason: '自动化验收：验证 D2 迁移后的申请链路', isTemp: 1 }
  })
  const requestId = submit.json?.data?.requestId
  check('yx 能提交 AUTO_UPDATE 申请（且无需客户端传 requestLevel）',
    submit.json?.code === 200 && Boolean(requestId),
    `code=${submit.json?.code} requestId=${requestId} msg=${submit.json?.msg}`)

  // 越权检查：申请里的 userId 必须由服务端按令牌覆盖
  const forged = await api('/lifecycle-api', '/permission/request/submit', {
    token: userToken,
    method: 'POST',
    body: { userId: 1, userName: 'admin', requestLevel: 0, requestReason: '越权尝试：替管理员申请', isTemp: 1 }
  })
  check('提交申请时 userId 被服务端按令牌覆盖（不能替他人申请）',
    forged.json?.code === 200 && Number(forged.json?.data?.userId) === 2,
    `code=${forged.json?.code} 实际归属 userId=${forged.json?.data?.userId}`)
  if (forged.json?.data?.requestId) {
    await api('/lifecycle-api', `/permission/request/${forged.json.data.requestId}`, { token: userToken, method: 'DELETE' })
  }

  if (!requestId) {
    // 前置失败时不要继续跑后面依赖 requestId 的断言，否则会得到一串假的 OK
    console.log('  !! 申请未创建成功，跳过后续审批相关断言')
  } else {
    // ---- admin 审批通过 ----
    const approve = await api('/lifecycle-api', `/permission/request/approve/${requestId}`, {
      token: adminToken,
      method: 'PUT',
      body: { approveNote: '自动化验收通过' }
    })
    check('admin 能审批通过该申请', approve.json?.code === 200, `code=${approve.json?.code}`)

    // ---- 关键不变量：审批通过不得把用户变成管理员 ----
    const levelAfterApprove = await roleLevelOf(userToken)
    check('★ 审批通过后 role_level 仍为 2（不得被改成 0）',
      levelAfterApprove === 2, `role_level=${levelAfterApprove}`)

    // ---- 临时权限确实生效（证明上一条不是"功能坏了"）----
    const granted = await api('/lifecycle-api', '/permission/request/list', { token: userToken })
    const active = (granted.json?.rows || []).filter((r) => String(r.status) === '1' && Number(r.isTemp) === 1)
    check('yx 已持有生效的临时权限记录（前端据此放行）', active.length > 0, `条数=${active.length}`)

    if (keyId) {
      const afterGrant = await tryAutoUpdate('1')
      check('★ 授权后能修改自动更新（临时权限真的生效了，不靠 role_level）',
        afterGrant.json?.code === 200, `code=${afterGrant.json?.code} msg=${afterGrant.json?.msg}`)
      await tryAutoUpdate('0') // 复位，避免留下副作用
    }

    // ---- 回退后仍不得造出已废弃的 1 级 ----
    const rollback = await api('/lifecycle-api', `/permission/request/rollback/${requestId}`, {
      token: userToken,
      method: 'PUT'
    })
    check('yx 能回退该临时权限', rollback.json?.code === 200, `code=${rollback.json?.code}`)

    const levelAfterRollback = await roleLevelOf(userToken)
    check('★ 回退后 role_level 仍为 2（且不得写成已废弃的 1）',
      levelAfterRollback === 2, `role_level=${levelAfterRollback}`)

    if (keyId) {
      const deniedAgain = await tryAutoUpdate('1')
      check('回退后自动更新权限被收回（且理由就是权限不足）',
        isDeniedWith(deniedAgain, '没有自动更新操作权限'),
        `code=${deniedAgain.json?.code} msg=${deniedAgain.json?.msg}`)
    }

    // ---- 清理：删掉本次申请，避免堆积 ----
    await api('/lifecycle-api', `/permission/request/${requestId}`, { token: userToken, method: 'DELETE' })
  }
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('P1 验收全部通过。\n')
