#!/usr/bin/env node
import { captchaFields } from './lib/captcha.mjs'
/**
 * 「更新密钥」与「自动更新权限」的边界验收（纯 HTTP，无浏览器依赖）
 * =============================================================================
 * 背景（2026-09-24 用户反馈的逻辑错误）
 * ------------------------------------
 * 用户只想改密钥名称，点「确认更新」却被拒，报错是「当前用户没有自动更新操作权限」。
 * 根因：后端把**请求里出现 autoUpdate 字段**当成「要改自动更新」，
 *       而前端的更新弹窗会把自动更新开关的当前值一并提交（恒非空）。
 *
 * 修复后要同时成立的两条（一放一拦，缺一不可）：
 *   A. 只改元数据（不带 autoUpdate，或带的正是库里当前值）→ **必须放行**
 *   B. 真的把 autoUpdate 改掉（值发生变化）        → **必须仍然拦住**
 * 只验 A 会退化成"把权限检查删掉"，只验 B 说明不了原来的 bug 修没修。
 *
 * 用例设计上刻意用**不具备自动更新权限的普通用户**（role_level=2）：
 * 用管理员跑这个脚本，A、B 都会通过，等于什么都没验。
 *
 * 用法: node tools/verify-update-vs-autoupdate.mjs [origin] [username] [password]
 * =============================================================================
 */
const ORIGIN = process.argv[2] || 'http://127.0.0.1'
const USER = process.argv[3] || 'acceptance_user'
const PASS = process.argv[4] || 'admin123'

/**
 * 一个**合法的** SM2 用户部分公钥（130 位十六进制、04 开头、在曲线上）。
 *
 * 为什么要写死一个：服务端会校验该点在曲线上，随手拼的十六进制会被拒
 * （"SM2 用户部分公钥不在曲线上"）。本次要验的是权限判定，
 * 不该在"造一把测试密钥"这一步上卡住。取自 tools/verify-p1.mjs 里同一常量。
 */
const VALID_UA =
  '04b038bd3450aff1c985e74918f6aeac37a6c05193c9c68654ab02dad094279177e8d692af475613983366ea67abc310e75b3c1fbe1ae51d4dda1519762f8e1b2e'

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
    /* 非 JSON 时保留 null，由调用方按 status 判断 */
  }
  return { status: res.status, json, text }
}

const isDeniedByPermission = (r) =>
  r.json?.code === 500 && String(r.json?.msg || '').includes('没有自动更新操作权限')

async function main() {
  console.log(`目标: ${ORIGIN}  用户: ${USER}\n`)

  // ---- 登录（令牌三端通用；验证码由 lib/captcha.mjs 代取）----
  const login = await api('/updatedel-api', '/login', {
    method: 'POST',
    // 登录要过图形验证码；脚本从 Redis 取答案（见 lib/captcha.mjs 的说明）
    body: { username: USER, password: PASS, ...(await captchaFields(ORIGIN, '/updatedel-api')) }
  })
  const token = login.json?.token
  check('以普通用户登录成功', Boolean(token), `code=${login.json?.code}`)
  if (!token) return

  // ---- 造一把属于该用户的密钥 ----
  const created = await api('/lifecycle-api', '/lifecycle/keymanage', {
    token,
    method: 'POST',
    body: {
      encrytType: '无证书非对称加密',
      encrytName: 'SM2',
      keyName: `verify-autoupdate-${Date.now()}`,
      keyUse: '验证用',
      keyDomain: 'A',
      ua: VALID_UA
    }
  })
  const keyId = created.json?.data?.key_id ?? created.json?.data?.keyId
  check(
    '创建一把测试密钥',
    Boolean(keyId),
    `keyId=${keyId} msg=${created.json?.msg || ''}`
  )
  if (!keyId) {
    // 失败时把原始响应打出来：这一层返回的是 snake_case（key_id/auto_update），
    // 前端有归一化、脚本没有 —— 只打印 "undefined" 会让人以为接口没返回数据。
    console.log('  原始响应: ' + created.text.slice(0, 400))
    return
  }

  const current = await api('/lifecycle-api', `/lifecycle/keymanage/${keyId}`, { token })
  const currentAutoUpdate = String(current.json?.data?.auto_update ?? current.json?.data?.autoUpdate ?? '0')
  console.log(`  （该密钥当前 autoUpdate=${currentAutoUpdate}）\n`)

  // ---- 用例 A1：完全不传 autoUpdate ----
  const a1 = await api('/lifecycle-api', '/lifecycle/keymanage', {
    token,
    method: 'PUT',
    body: { keyId, keyName: `改名-${Date.now()}`, keyUse: '验证用' }
  })
  check(
    'A1 只改元数据（不传 autoUpdate）→ 放行',
    a1.json?.code === 200,
    `code=${a1.json?.code} msg=${a1.json?.msg || ''}`
  )

  // ---- 用例 A2：带上 autoUpdate，但值与库里相同（旧实现就是在这里误拦的）----
  const a2 = await api('/lifecycle-api', '/lifecycle/keymanage', {
    token,
    method: 'PUT',
    body: { keyId, keyName: `改名2-${Date.now()}`, autoUpdate: currentAutoUpdate }
  })
  check(
    'A2 带上未变化的 autoUpdate → 放行（用户遇到的正是这一条）',
    a2.json?.code === 200,
    `code=${a2.json?.code} msg=${a2.json?.msg || ''}`
  )

  // ---- 用例 A3：等价写法也不该被误判成"变了" ----
  const equivalent = currentAutoUpdate === '1' ? 'true' : 'false'
  const a3 = await api('/lifecycle-api', '/lifecycle/keymanage', {
    token,
    method: 'PUT',
    body: { keyId, keyName: `改名3-${Date.now()}`, autoUpdate: equivalent }
  })
  check(
    `A3 autoUpdate 用等价写法（'${equivalent}' 等价于 '${currentAutoUpdate}'）→ 放行`,
    a3.json?.code === 200,
    `code=${a3.json?.code} msg=${a3.json?.msg || ''}`
  )

  // ---- 用例 B：真的改值 → 必须仍然被权限拦住（防绕过不能被修没）----
  const flipped = currentAutoUpdate === '1' ? '0' : '1'
  const b = await api('/lifecycle-api', '/lifecycle/keymanage', {
    token,
    method: 'PUT',
    body: { keyId, keyName: `改名4-${Date.now()}`, autoUpdate: flipped }
  })
  check(
    `B 真的把 autoUpdate 改成 ${flipped} → 仍被权限拦下`,
    isDeniedByPermission(b),
    `code=${b.json?.code} msg=${b.json?.msg || ''}`
  )

  // ---- 清理：回收这把测试密钥 ----
  const revoked = await api('/lifecycle-api', `/lifecycle/keymanage/${keyId}`, { token, method: 'DELETE' })
  check('清理测试密钥（回收）', revoked.json?.code === 200, `code=${revoked.json?.code}`)

  console.log(`\n结果: ${pass} 通过 / ${fail} 失败`)
  if (fail) {
    console.log('失败项:')
    failures.forEach((f) => console.log('  - ' + f))
    process.exit(1)
  }
}

main().catch((e) => {
  console.error('脚本异常:', e.message)
  process.exit(1)
})
