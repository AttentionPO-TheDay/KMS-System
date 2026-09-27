#!/usr/bin/env node
/**
 * 重新登记一批**干净的演示密钥**（清空旧数据之后使用）
 * =============================================================================
 * 背景：早期那批密钥全部是 ms_v1 + 随机 SSCL 域参数签发的，用户侧本地份额 `u`
 * 从未持久化，因此从解密角度本来就不可用；且相当一部分共用同一个 `ua`。
 * 决定是"清空 + 重新登记"，而不是逐条抢救。
 *
 * 本脚本通过**真实接口**登记密钥，因此：
 *   * 新记录会带上 ms_v2 / v1_derived_sscl_domain / active 三个版本标记；
 *   * 材料是真的（SM2 走 KGC 部分私钥，SSCL 走确定性域参数）；
 *   * 每把密钥使用**各自独立的 `ua`**（本地份额对应的公钥），
 *     避免重演"多把密钥共用一个 ua"的旧问题。
 *
 * ⚠️ 这里生成的 `ua` 对应的**私钥份额 u 不会被保存**（脚本用完即弃）。
 *    这与现有前端行为一致 —— 用户必须自己保存弹出的 `d_a`。
 *    P3 会补上正式的密钥文件导出/导入机制，届时这段会被替换掉。
 *
 * 用法：node kms-ops/tests/seed-demo-keys.mjs [origin]
 * =============================================================================
 */

const ORIGIN = process.argv[2] || 'http://127.0.0.1'

// sm2p256v1 曲线参数（与前端 GenerateView.vue 中的常量一致）
const P = BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF')
const A = BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC')
const B = BigInt('0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93')
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
  if (oldR !== 1n) throw new Error('modInverse: 不可逆')
  return ((oldS % m) + m) % m
}

/** 椭圆曲线点加（仿射坐标，无穷远点用 null 表示） */
function pointAdd(p1, p2) {
  if (p1 === null) return p2
  if (p2 === null) return p1
  const [x1, y1] = p1
  const [x2, y2] = p2
  let lambda
  if (x1 === x2 && mod(y1 + y2) === 0n) return null
  if (x1 === x2 && y1 === y2) {
    lambda = mod((3n * x1 * x1 + A) * modInverse(2n * y1, P))
  } else {
    lambda = mod((y2 - y1) * modInverse(x2 - x1, P))
  }
  const x3 = mod(lambda * lambda - x1 - x2)
  const y3 = mod(lambda * (x1 - x3) - y1)
  return [x3, y3]
}

/** 标量乘（double-and-add） */
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
const G = [GX, GY]

/** 生成一对本地份额：返回 { ua: '04...' 压缩点, u: 私钥份额 } */
function generateLocalShare() {
  // 用密码学安全随机取标量（Node 的 crypto 不参与 DSH 沙箱限制）
  const bytes = new Uint8Array(32)
  globalThis.crypto.getRandomValues(bytes)
  let u = 0n
  for (const byte of bytes) u = (u << 8n) | BigInt(byte)
  u = modN(u)
  if (u === 0n) return generateLocalShare()
  const point = pointMul(u, G)
  return { ua: '04' + hex64(point[0]) + hex64(point[1]), u }
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
    /* ignore */
  }
  return { status: res.status, json, text }
}

async function login(username, password) {
  const res = await api('/lifecycle-api', '/login', { method: 'POST', body: { username, password } })
  if (!res.json?.token) throw new Error(`登录失败 ${username}: ${res.text.slice(0, 150)}`)
  return res.json.token
}

// ---------------------------------------------------------------------------
// 计划登记的密钥：(用户, 算法, 名称)
// ---------------------------------------------------------------------------
const PLAN = [
  ['yx', 'SM2', '演示密钥-个人签名'],
  ['yx', 'SM2', '演示密钥-数据加密'],
  ['yx', 'SSCL', '演示密钥-域内协商'],
  ['acceptance_user', 'SM2', '演示密钥-验收签名'],
  ['acceptance_user', 'SSCL', '演示密钥-验收协商'],
  ['admin', 'SM2', '演示密钥-管理员签名'],
  ['admin', 'SSCL', '演示密钥-管理员协商'],
  ['test', 'SM2', '演示密钥-演示账户'],
  ['user01', 'SM2', '演示密钥-普通用户'],
  ['test01', 'SSCL', '演示密钥-测试账户']
]
const PASSWORDS = { user01: null, test01: null } // 这两个账号口令未知，跳过

const tokens = new Map()
async function tokenFor(user) {
  if (tokens.has(user)) return tokens.get(user)
  const token = await login(user, 'admin123')
  tokens.set(user, token)
  return token
}

console.log(`\n=== 重新登记演示密钥 @ ${ORIGIN} ===\n`)

let created = 0
let skipped = 0
for (const [user, algorithm, keyName] of PLAN) {
  if (user in PASSWORDS && PASSWORDS[user] === null && !['admin', 'yx', 'acceptance_user', 'test'].includes(user)) {
    console.log(`  [SKIP] ${user} 口令未知，跳过 ${keyName}`)
    skipped++
    continue
  }
  let token
  try {
    token = await tokenFor(user)
  } catch (e) {
    console.log(`  [SKIP] ${user}: ${e.message}`)
    skipped++
    continue
  }

  const share = generateLocalShare()
  const res = await api('/generate-api', '/generate/keymanage', {
    token,
    method: 'POST',
    body: {
      encrytType: '无证书非对称加密',
      encrytName: algorithm,
      keyName,
      keyUse: '演示数据',
      keyDomain: 'A',
      uA: share.ua
    }
  })
  if (res.json?.code === 200) {
    created++
    console.log(`  [OK]   ${user} / ${algorithm} / ${keyName}   ua=${share.ua.slice(0, 14)}…`)
  } else {
    console.log(`  [FAIL] ${user} / ${algorithm} / ${keyName}: ${res.json?.msg || res.text.slice(0, 120)}`)
    skipped++
  }
  // 落库走 Kafka，稍等以免一次投递过多
  await new Promise((r) => setTimeout(r, 400))
}

console.log(`\n投递完成：${created} 条已提交，${skipped} 条跳过（Kafka 异步落库，稍后核对）`)
console.log('提示：`ua` 对应的私钥份额 u 未被保存 —— 与现有前端行为一致，P3 会补正式的密钥文件机制。\n')