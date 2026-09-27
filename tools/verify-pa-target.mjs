#!/usr/bin/env node
/**
 * 加密目标点验收（计划 §7 P3 步骤 0 / 风险 R16）
 * =============================================================================
 * 这是整个用户腿分发的**地基**。计划原文写的是"加密必须用 finalPublicKey"，
 * 而 P0-B 用实验证伪了它：`W_A`（即 finalPublicKey）**没有对应的私钥**，
 * 拿它加密会做出**谁都打不开**的信封 —— 连用户自己也不行。
 *
 * 正确的目标是 `P_A = W_A + λ·P_pub`，而它必须满足一条**可判定的性质**：
 *
 *        P_A == d_A · G          其中 d_A = (t_A + u) mod n
 *
 * 本脚本就验这一条 —— 而不是"接口返回了个 130 位十六进制串"这种表面检查。
 *
 * 做法：
 *   1. 脚本自己生成一个本地份额 `u`（**并保留它**），用它的公钥 `u·G` 登记一把 SM2 密钥；
 *   2. 以属主身份读回 `t_A`（partialKey）与 `W_A`（finalPublicKey）；
 *   3. 算出 `d_A = (t_A + u) mod n`，再算 `d_A·G`；
 *   4. 从内部接口取服务端给出的加密目标 `P_A`；
 *   5. 断言 `d_A·G == P_A`。
 *
 * 同时断言 `P_A != W_A`（这条就是 R16 的直接证据：两者确实不同，
 * 用错的那一个会毁掉整个信封）。
 *
 * 用法：node tools/verify-pa-target.mjs [origin]
 * =============================================================================
 */

import { captchaFields } from './lib/captcha.mjs'
import { readFileSync } from 'node:fs'

const ORIGIN = process.argv[2] || 'http://127.0.0.1'
const INTERNAL_ORIGIN = process.argv[3] || 'http://127.0.0.1:9082'

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
// sm2p256v1 曲线运算（与 kms-ops/tests/seed-demo-keys.mjs 同一套实现）
// ---------------------------------------------------------------------------
const P = BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF')
const A = BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC')
const N = BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123')
const GX = BigInt('0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7')
const GY = BigInt('0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0')
const mod = (v) => ((v % P) + P) % P
const modN = (v) => ((v % N) + N) % N

function modInverse(a, m) {
  let [oldR, r] = [((a % m) + m) % m, m]
  let [oldS, s] = [1n, 0n]
  while (r !== 0n) {
    const q = oldR / r
    ;[oldR, r] = [r, oldR - q * r]
    ;[oldS, s] = [s, oldS - q * s]
  }
  if (oldR !== 1n) throw new Error('modInverse 不可逆')
  return ((oldS % m) + m) % m
}

function pointAdd(p1, p2) {
  if (p1 === null) return p2
  if (p2 === null) return p1
  const [x1, y1] = p1
  const [x2, y2] = p2
  let lam
  if (x1 === x2 && mod(y1 + y2) === 0n) return null
  if (x1 === x2 && y1 === y2) {
    lam = mod((3n * x1 * x1 + A) * modInverse(2n * y1, P))
  } else {
    lam = mod((y2 - y1) * modInverse(x2 - x1, P))
  }
  const x3 = mod(lam * lam - x1 - x2)
  return [x3, mod(lam * (x1 - x3) - y1)]
}

function pointMul(k, point) {
  let result = null
  let addend = point
  let n = modN(k)
  while (n > 0n) {
    if (n & 1n) result = pointAdd(result, addend)
    addend = pointAdd(addend, addend)
    n >>= 1n
  }
  return result
}

const hex64 = (v) => v.toString(16).padStart(64, '0')
const pointHex = (pt) => '04' + hex64(pt[0]) + hex64(pt[1])
const G = [GX, GY]

function randomScalar() {
  const bytes = new Uint8Array(32)
  globalThis.crypto.getRandomValues(bytes)
  let v = 0n
  for (const b of bytes) v = (v << 8n) | BigInt(b)
  v = modN(v)
  return v === 0n ? randomScalar() : v
}

// ---------------------------------------------------------------------------
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
    /* ignore */
  }
  return { status: res.status, json, text }
}

async function login(username, password) {
  const res = await api('/lifecycle-api', '/login', { method: 'POST', body: { username, password, ...(await captchaFields(ORIGIN)) } })
  if (!res.json?.token) throw new Error(`登录失败 ${username}`)
  return res.json.token
}

/** 调内部接口取 P_A。注意 RuoYi 约定：错误也可能包在 HTTP 200 的 body.code 里。 */
async function fetchPa(keyId, token) {
  const headers = token ? { 'X-Internal-Token': token } : {}
  const res = await fetch(`${INTERNAL_ORIGIN}/internal/lifecycle/user-public-key?keyId=${keyId}`, { headers })
  const json = await res.json().catch(() => null)
  return { httpStatus: res.status, json, data: json?.data }
}

const internalToken = (() => {
  const text = readFileSync(new URL('../kms-ops/.env', import.meta.url), 'utf8')
  const line = text.split(/\r?\n/).find((l) => l.startsWith('INTERNAL_TOKEN='))
  return line ? line.slice('INTERNAL_TOKEN='.length).trim() : ''
})()

console.log(`\n=== 加密目标点验收 @ ${ORIGIN} ===\n`)
if (!internalToken) {
  console.log('  !! kms-ops/.env 里没有 INTERNAL_TOKEN，无法调用内部接口')
  process.exit(1)
}

const yxToken = await login('yx', 'admin123')

// ---------------------------------------------------------------------------
// 1. 登记一把**保留本地份额 u** 的 SM2 密钥
// ---------------------------------------------------------------------------
const u = randomScalar()
const ua = pointHex(pointMul(u, G))
const KEY_NAME = `verify-pa-目标点-${Date.now()}`
console.log(`1. 登记测试密钥（保留本地份额 u，长度 ${u.toString(16).length} 位十六进制）`)

const created = await api('/generate-api', '/generate/keymanage', {
  token: yxToken,
  method: 'POST',
  body: {
    encrytType: '无证书非对称加密',
    encrytName: 'SM2',
    keyName: KEY_NAME,
    keyUse: '自动化验收',
    keyDomain: 'A',
    uA: ua
  }
})
check('密钥登记请求已提交', created.json?.code === 200, `code=${created.json?.code}`)

let keyId = null
for (let i = 0; i < 25 && !keyId; i++) {
  await new Promise((r) => setTimeout(r, 700))
  const list = await api('/generate-api', '/generate/key/list?pageSize=100', { token: yxToken })
  const hit = (list.json?.rows || []).find((k) => k.keyName === KEY_NAME)
  keyId = hit?.keyId || null
}
check('密钥已入库（Kafka 异步落库完成）', Boolean(keyId), `keyId=${keyId}`)

if (!keyId) {
  console.log('\n没有 keyId，后续断言无法进行')
  process.exit(1)
}

// ---------------------------------------------------------------------------
// 2. 读回 t_A 与 W_A（属主身份，材料保留）
// ---------------------------------------------------------------------------
console.log('\n2. 以属主身份读回密钥材料')
const detail = await api('/lifecycle-api', `/lifecycle/keymanage/${keyId}`, { token: yxToken })
const entity = detail.json?.data
const materialRaw = entity?.key_value ?? entity?.keyValue
let material = materialRaw
if (typeof materialRaw === 'string') {
  try {
    material = JSON.parse(materialRaw)
  } catch {
    material = null
  }
}
check('能读到 partialKey（t_A）与 finalPublicKey（W_A）',
  Boolean(material?.partialKey && material?.finalPublicKey),
  `keys=${material ? Object.keys(material).join(',') : 'n/a'}`)

if (!material?.partialKey || !material?.finalPublicKey) {
  console.log('\n缺少密钥材料，后续断言无法进行')
  process.exit(1)
}

const tA = BigInt('0x' + material.partialKey)
const wA = material.finalPublicKey.toLowerCase()

// ---------------------------------------------------------------------------
// 3. 服务端给出的加密目标点
// ---------------------------------------------------------------------------
console.log('\n3. 取服务端给出的加密目标点 P_A')
const paRes = await fetchPa(keyId, internalToken)
const pa = paRes.data?.publicKey

check('内部接口返回成功', paRes.data?.ok === true,
  paRes.data?.errorMessage || `publicKeyId=${paRes.data?.publicKeyId}`)
check('P_A 是 04 开头的 130 位十六进制点', /^04[0-9a-f]{128}$/.test(String(pa || '')),
  String(pa || '').slice(0, 20) + '…')

// ---------------------------------------------------------------------------
// 4. ★ 决定性断言：P_A == d_A · G
// ---------------------------------------------------------------------------
console.log('\n4. ★ 决定性断言：服务端给的 P_A 是否真的对应用户的私钥')
{
  const dA = modN(tA + u)
  const dAG = pointHex(pointMul(dA, G))
  check('★ P_A == d_A · G （d_A = (t_A + u) mod n）',
    String(pa).toLowerCase() === dAG.toLowerCase(),
    String(pa).toLowerCase() === dAG.toLowerCase()
      ? '完全一致 —— 用户确实能用 d_A 解开加密到该点的信封'
      : `P_A=${String(pa).slice(0, 24)}…  d_A·G=${dAG.slice(0, 24)}…`)

  // R16 的直接证据：如果两者相同，说明服务端返回的还是 W_A，那是错的
  check('★ P_A != W_A（finalPublicKey）—— 这正是计划原文写错的那一处',
    String(pa).toLowerCase() !== wA,
    `P_A=${String(pa).slice(0, 18)}…  W_A=${wA.slice(0, 18)}…`)

  // 反向证据：用 W_A 当作加密目标，用户**解不开**（结构上就不成立）
  const dAOnWA = pointHex(pointMul(dA, G))
  check('用 W_A 作为目标点算不出 d_A·G（证明 W_A 不是可用目标）',
    wA !== dAOnWA)
}

// ---------------------------------------------------------------------------
// 5. 鉴权与 D17 的服务端收窄
// ---------------------------------------------------------------------------
console.log('\n5. 鉴权与算法收窄（服务端强制）')
{
  const noToken = await fetchPa(keyId, '')
  check('不带令牌 → 被拒（RuoYi 把错误放在 HTTP 200 的 body.code 里）',
    noToken.data?.ok !== true && noToken.json?.code !== 200,
    `body.code=${noToken.json?.code} msg=${noToken.json?.msg}`)

  const badToken = await fetchPa(keyId, 'definitely-wrong')
  check('错误令牌 → 被拒', badToken.data?.ok !== true, `body.code=${badToken.json?.code}`)

  const missing = await fetchPa(999999, internalToken)
  check('不存在的密钥 → 明确报错而不是返回空点',
    missing.data?.ok === false && missing.data?.errorCode === 'KEY_NOT_FOUND',
    `errorCode=${missing.data?.errorCode}`)

  // D17：找一把非 SM2/SSCL 的密钥（如果有）验证收窄；
  // 当前库里只有 SM2/SSCL，所以这条用"不存在的算法"无法构造，
  // 改为确认接口对 SSCL 也能正确返回（覆盖另一条分支）。
  const ssclToken = await api('/generate-api', '/generate/key/list?pageSize=100', { token: yxToken })
  const sscl = (ssclToken.json?.rows || []).find((k) => k.encrytName === 'SSCL')
  if (sscl) {
    const ssclPa = await fetchPa(sscl.keyId, internalToken)
    check('SSCL 分支同样能算出 P_A（走的是 SSCLEA 那条，不依赖 ms）',
      ssclPa.data?.ok === true && /^04[0-9a-f]{128}$/.test(String(ssclPa.data?.publicKey || '')),
      String(ssclPa.data?.publicKey || '').slice(0, 20) + '…')
  } else {
    console.log('  [SKIP] 当前没有 SSCL 密钥，跳过该分支')
  }
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('加密目标点正确：服务端给出的 P_A 正是用户私钥 d_A 对应的公开点。\n')