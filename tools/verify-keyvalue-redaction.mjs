#!/usr/bin/env node
import { captchaFields } from './lib/captcha.mjs'
/**
 * `key_value` 脱敏验收（计划 §8 R18 / 本次插队项 B2）
 * =============================================================================
 * `keymanage.key_value` 是**密钥材料**，不是普通字段。它的内容按算法差别很大：
 *   - SM2 / SSCL：KGC 分片（partialKey / SSCLKey / SSCLEA）—— 属主需要它来现算 d_A
 *   - CL-Kyber / CL-Falcon：**完整私钥**
 *
 * 本脚本验证四类接口的行为：
 *   1. 列表         → 一律不带材料
 *   2. 详情 · 属主  → SM2/SSCL 保留材料（否则客户端的"算最终私钥"功能会坏）
 *   3. 详情 · 非属主（管理员看别人的）→ 降级为公钥视图，且显式标注 redacted
 *   4. 安全分析 DTO → 它内嵌了整条 Keymanage，同样必须脱敏（否则是绕过列表脱敏的后门）
 *   5. 创建响应     → 仍返回材料（客户端依赖它计算 d_A，这条不能被"顺手"改掉）
 *
 * 用法：node tools/verify-keyvalue-redaction.mjs [origin]
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
    /* 非 JSON 时保留 null，由调用方按 code 判断 */
  }
  return { status: res.status, json, text }
}

async function login(username, password) {
  const res = await api('/lifecycle-api', '/login', { method: 'POST', body: { username, password, ...(await captchaFields(ORIGIN)) } })
  if (!res.json?.token) throw new Error(`登录失败 ${username}: ${res.text.slice(0, 150)}`)
  return res.json.token
}

/** 材料特征：出现这些键就说明响应里带出了密钥材料 */
const MATERIAL_MARKERS = ['partialKey', 'SSCLEA', 'SSCLKey', 'private_key', 'privateKey', 'kgcRandomW', 'kgcLambda', 'kgcMx']
function materialMarkersIn(value) {
  if (typeof value !== 'string' || !value) return []
  return MATERIAL_MARKERS.filter((m) => value.includes(m))
}

/**
 * 取一条记录里的 key_value。
 *
 * **两个模块的 JSON 命名不同，必须都认**：
 *   - kms-generate 的 Keymanage 用 Lombok 默认 getter → 字段名是 `keyValue`
 *   - kms-updatedel 的 Keymanage 带 `@JsonProperty("key_value")` → 字段名是 `key_value`
 * 早期版本的脚本只读 `keyValue`，于是对生命周期接口的断言全部"通过"——
 * 但那是因为读到的是 undefined，属于**假通过**。
 */
function materialOf(entity) {
  if (!entity || typeof entity !== 'object') return undefined
  return entity.keyValue !== undefined ? entity.keyValue : entity.key_value
}
/** 是否是我们约定的"已脱敏"信封 */
function isRedactedEnvelope(value) {
  if (typeof value !== 'string' || !value) return false
  try {
    return JSON.parse(value)?.redacted === true
  } catch {
    return false
  }
}

console.log(`\n=== key_value 脱敏验收 @ ${ORIGIN} ===\n`)

const adminToken = await login('admin', 'admin123')
const yxToken = await login('yx', 'admin123')
console.log('  登录成功：admin / yx\n')

// ---------------------------------------------------------------------------
// 准备：确保 yx 有一把自己的 SM2 密钥（沿用 verify-p1 的幂等做法）
// ---------------------------------------------------------------------------
const TEST_KEY_NAME = 'verify-p1-D2-临时测试密钥'
const VALID_UA =
  '04b038bd3450aff1c985e74918f6aeac37a6c05193c9c68654ab02dad094279177e8d692af475613983366ea67abc310e75b3c1fbe1ae51d4dda1519762f8e1b2e'

let yxKeyId = null
let createResponseMaterial = ''
{
  const list = await api('/generate-api', '/generate/key/list?pageSize=100', { token: yxToken })
  const rows = list.json?.rows || []
  const hit = rows.find((k) => k.keyName === TEST_KEY_NAME)
  yxKeyId = hit ? hit.keyId : null
  if (!yxKeyId) {
    const created = await api('/generate-api', '/generate/keymanage', {
      token: yxToken,
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
    createResponseMaterial = created.json?.data?.keyValue || ''
    for (let i = 0; i < 20 && !yxKeyId; i++) {
      await new Promise((r) => setTimeout(r, 700))
      const again = await api('/generate-api', '/generate/key/list?pageSize=100', { token: yxToken })
      const h = (again.json?.rows || []).find((k) => k.keyName === TEST_KEY_NAME)
      yxKeyId = h ? h.keyId : null
    }
  }
}
check('能为 yx 准备一把测试密钥（后续断言的前提）', Boolean(yxKeyId), `keyId=${yxKeyId}`)

// ---------------------------------------------------------------------------
// 1. 列表：一律不带材料
// ---------------------------------------------------------------------------
console.log('1. 列表接口不得带出密钥材料')
{
  const targets = [
    ['/generate-api', '/generate/key/list?pageSize=100', yxToken, 'GET /generate/key/list'],
    ['/generate-api', '/generate/keymanage/list?pageSize=100', yxToken, 'GET /generate/keymanage/list'],
    ['/lifecycle-api', '/lifecycle/keymanage/list?pageSize=100', yxToken, 'GET /lifecycle/keymanage/list'],
    ['/lifecycle-api', '/lifecycle/keymanage/list?pageSize=100', adminToken, 'GET /lifecycle/keymanage/list (admin)']
  ]
  for (const [base, path, token, label] of targets) {
    const res = await api(base, path, { token })
    const rows = res.json?.rows || []
    const leaked = rows.filter((r) => materialMarkersIn(materialOf(r)).length > 0)
    check(`${label} 无密钥材料`, res.json?.code === 200 && leaked.length === 0,
      `rows=${rows.length} 含材料行=${leaked.length}`)
  }
}

// ---------------------------------------------------------------------------
// 2/3. 详情：属主保留、非属主脱敏
// ---------------------------------------------------------------------------
console.log('\n2/3. 详情接口按「属主 + 算法」区分')
if (yxKeyId) {
  const own = await api('/generate-api', `/generate/key/${yxKeyId}`, { token: yxToken })
  const ownValue = materialOf(own.json?.data)
  check('属主读自己的 SM2 密钥：**保留**材料（客户端要靠它算 d_A）',
    materialMarkersIn(ownValue).includes('partialKey'), `markers=${JSON.stringify(materialMarkersIn(ownValue))}`)

  const other = await api('/generate-api', `/generate/key/${yxKeyId}`, { token: adminToken })
  const otherValue = materialOf(other.json?.data)
  check('管理员读他人密钥：材料已脱敏',
    other.json?.code === 200 && materialMarkersIn(otherValue).length === 0,
    `markers=${JSON.stringify(materialMarkersIn(otherValue))}`)
  check('管理员读他人密钥：返回的是显式 redacted 信封（不是 null，便于前端区分）',
    isRedactedEnvelope(otherValue), `keyValue=${String(otherValue).slice(0, 80)}`)

  const ownLifecycle = await api('/lifecycle-api', `/lifecycle/keymanage/${yxKeyId}`, { token: yxToken })
  const ownLifecycleValue = materialOf(ownLifecycle.json?.data)
  check('属主读生命周期详情：保留材料（注意该模块 JSON 是 snake_case）',
    materialMarkersIn(ownLifecycleValue).includes('partialKey'),
    `markers=${JSON.stringify(materialMarkersIn(ownLifecycleValue))} len=${String(ownLifecycleValue || '').length}`)

  const adminLifecycle = await api('/lifecycle-api', `/lifecycle/keymanage/${yxKeyId}`, { token: adminToken })
  const adminLifecycleValue = materialOf(adminLifecycle.json?.data)
  check('管理员读生命周期详情：材料已脱敏（且确实是 redacted 信封，不是字段缺失）',
    materialMarkersIn(adminLifecycleValue).length === 0 && isRedactedEnvelope(adminLifecycleValue),
    `markers=${JSON.stringify(materialMarkersIn(adminLifecycleValue))}`)
} else {
  console.log('  !! 没有可用密钥，跳过详情断言')
}

// ---------------------------------------------------------------------------
// 4. 安全分析 DTO（内嵌 Keymanage，是绕过列表脱敏的后门）
// ---------------------------------------------------------------------------
console.log('\n4. 安全分析 DTO 的 baseInfo 同样要脱敏')
if (yxKeyId) {
  const analysis = await api('/lifecycle-api', `/lifecycle/keymanage/analysis/${yxKeyId}`, { token: adminToken })
  const base = analysis.json?.data?.baseInfo
  const baseValue = materialOf(base)
  check('管理员读安全分析：baseInfo 的材料已脱敏',
    !base || materialMarkersIn(baseValue).length === 0,
    `markers=${JSON.stringify(materialMarkersIn(baseValue))}`)
  check('安全分析本身仍可用（证明上面的脱敏不是把接口搞坏了）',
    analysis.json?.code === 200 && Boolean(base), `code=${analysis.json?.code}`)
}

// ---------------------------------------------------------------------------
// 5. 创建响应不能被"顺手"脱敏（客户端依赖它）
// ---------------------------------------------------------------------------
console.log('\n5. 创建/更新响应仍须返回材料')
{
  const created = await api('/generate-api', '/generate/keymanage', {
    token: yxToken,
    method: 'POST',
    body: {
      encrytType: '无证书非对称加密',
      encrytName: 'SM2',
      keyName: 'verify-redaction-创建响应检查',
      keyUse: '自动化验收',
      keyDomain: 'A',
      uA: VALID_UA
    }
  })
  const value = materialOf(created.json?.data) || createResponseMaterial
  check('创建响应仍带 material（否则客户端的"算最终私钥"会坏）',
    created.json?.code === 200 && materialMarkersIn(value).includes('partialKey'),
    `code=${created.json?.code} markers=${JSON.stringify(materialMarkersIn(value))}`)
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('key_value 脱敏行为符合预期。\n')