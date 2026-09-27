#!/usr/bin/env node
import { captchaFields } from './lib/captcha.mjs'
/**
 * SSCL 域参数一致性验收（本轮插队项 B3）
 * =============================================================================
 * SSCL 把一个 t 次多项式的份额当作公开参数发布，域秘密藏在常数项里。
 * 客户端（浏览器）做的事是：拿 `/comparam` 发布的 t 个点 `(xIndexs[i], yIndexs[i])`，
 * 加上自己密钥里的点 `(mx, my)`，在 x=0 处做拉格朗日插值，
 * 得到的常数项**必须等于密钥里存的 `SSCLEA`**。
 *
 * 一旦"发布参数的那条多项式"与"生成密钥材料时用的那条多项式"不是同一条，
 * 插值结果就是垃圾，密钥直接不可用。这正是修复前的状态：
 *   - Go 服务发布 /comparam，却与 Java 各用一条随机多项式；
 *   - 而且两边都随进程启动重新随机，重启即漂移。
 *
 * 本脚本验证两条性质：
 *   1. **重启稳定**：/comparam 在服务重启后逐字节不变
 *      （由调用方在脚本外重启，见 tools/README 或计划文档；这里只校验当前值可复现）
 *   2. **插值自洽**：用浏览器那套插值算法，能从发布的点 + 密钥自身的点
 *      还原出密钥里存的 SSCLEA
 *
 * 第 2 条是真正重要的那条 —— 它同时覆盖"Go 与 Java 是否共用一条多项式"。
 *
 * 用法：node tools/verify-sscl-params.mjs [origin]
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
    /* 保留 null */
  }
  return { status: res.status, json, text }
}

async function login(username, password) {
  const res = await api('/lifecycle-api', '/login', { method: 'POST', body: { username, password, ...(await captchaFields(ORIGIN)) } })
  if (!res.json?.token) throw new Error(`登录失败 ${username}: ${res.text.slice(0, 150)}`)
  return res.json.token
}

// ---------------------------------------------------------------------------
// SM2 曲线阶 n（sm2p256v1）—— 与前端 GenerateView.vue 里的常量一致
// ---------------------------------------------------------------------------
const N = BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123')

/** 模幂：BigInt 没有内置的 modPow */
function modPow(base, exp, mod) {
  let result = 1n
  let b = ((base % mod) + mod) % mod
  let e = exp
  while (e > 0n) {
    if (e & 1n) result = (result * b) % mod
    b = (b * b) % mod
    e >>= 1n
  }
  return result
}

/** 扩展欧几里得求模逆 */
function modInverse(a, mod) {
  let [old_r, r] = [((a % mod) + mod) % mod, mod]
  let [old_s, s] = [1n, 0n]
  while (r !== 0n) {
    const q = old_r / r
    ;[old_r, r] = [r, old_r - q * r]
    ;[old_s, s] = [s, old_s - q * s]
  }
  if (old_r !== 1n) throw new Error('模逆不存在（点可能重合）')
  return ((old_s % mod) + mod) % mod
}

/**
 * 与浏览器 `getsecret()` 完全同构的拉格朗日插值（求 x=0 处的值）。
 * 对应 kms-user/front/src/views/generate/GenerateView.vue 里的 getsecret。
 */
function interpolateAtZero(xPoints, yPoints, mod) {
  if (xPoints.length !== yPoints.length) throw new Error('x/y 点数不一致')
  const t = xPoints.length - 1
  let secret = 0n
  for (let i = 0; i <= t; i++) {
    let numerator = 1n
    let denominator = 1n
    for (let j = 0; j <= t; j++) {
      if (i === j) continue
      numerator = (numerator * ((-xPoints[j] % mod) + mod)) % mod
      const diff = (((xPoints[i] - xPoints[j]) % mod) + mod) % mod
      denominator = (denominator * diff) % mod
    }
    const inv = modInverse(denominator, mod)
    const li = (numerator * inv) % mod
    secret = (secret + yPoints[i] * li) % mod
  }
  return secret
}

/**
 * 取 /comparam 并归一化。
 *
 * ⚠️ 响应形状容易踩坑，实测（不是照文档猜的）：
 *   - 前端走 `/generate/keymanage/comparam`，经 Java 兼容层 `normalizeGoComParam` 归一化；
 *   - 归一化后字段名是 **`xIndex` / `yIndex`（单数）**，值是**十六进制定长字符串**；
 *   - 而且这两个字段是**字符串形式的 JSON 数组**（`"[\"a1da…\", …]"`），
 *     所以前端才要写 `JSON.parse(response.xIndex)`。
 *   - Go 原始接口用的是 `xIndexs` / `yIndexs`、且是十进制数。
 * 这里对两种命名都兼容，并按"字符串就先 JSON.parse、元素按 hex 解析"处理。
 */
function normalizeIndexList(raw) {
  let value = raw
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value)
    } catch {
      throw new Error(`索引字段不是合法 JSON: ${String(raw).slice(0, 80)}`)
    }
  }
  if (!Array.isArray(value)) {
    throw new Error(`索引字段不是数组: ${typeof value}`)
  }
  // 元素可能是 hex 字符串（Java 归一化）或十进制数字（Go 原样）
  return value.map((item) => {
    const text = String(item).trim()
    return /^[0-9a-fA-F]+$/.test(text) && text.length >= 32 ? BigInt('0x' + text) : BigInt(text)
  })
}

async function fetchComParam() {
  const token = await login('yx', 'admin123')
  const res = await api('/generate-api', '/generate/keymanage/comparam', {
    token,
    method: 'POST',
    body: { encrytType: '无证书非对称加密', encrytName: 'SSCL' }
  })
  let data = res.json?.data
  if (typeof data === 'string') data = JSON.parse(data)
  const rawX = data?.xIndex ?? data?.xIndexs
  const rawY = data?.yIndex ?? data?.yIndexs
  if (rawX == null || rawY == null) {
    throw new Error(`/comparam 未返回索引数组: ${JSON.stringify(res.json).slice(0, 200)}`)
  }
  return { token, data, xs: normalizeIndexList(rawX), ys: normalizeIndexList(rawY) }
}

console.log(`\n=== SSCL 域参数一致性验收 @ ${ORIGIN} ===\n`)

// ---------------------------------------------------------------------------
// 1. /comparam 自身可复现（同一进程内两次调用必须一致）
// ---------------------------------------------------------------------------
const first = await fetchComParam()
const second = await fetchComParam()
check(
  '/comparam 两次调用完全一致（同进程内稳定）',
  JSON.stringify(first.xs.map(String)) === JSON.stringify(second.xs.map(String)) &&
    JSON.stringify(first.ys.map(String)) === JSON.stringify(second.ys.map(String)),
  `T=${first.xs.length}`
)
check('xIndex 与 yIndex 数量一致', first.xs.length === first.ys.length,
  `x=${first.xs.length} y=${first.ys.length}`)

// x 必须两两不同，否则插值时要算的模逆不存在
const xs = first.xs
check('xIndex 两两互不相同', new Set(xs.map(String)).size === xs.length,
  `unique=${new Set(xs.map(String)).size}/${xs.length}`)
check('xIndex 均落在 [1, n) 内', xs.every((v) => v > 0n && v < N), `n=${N.toString(16).slice(0, 16)}…`)

// ---------------------------------------------------------------------------
// 2. 关键性质：生成一把 SSCL 密钥，然后按浏览器算法插值还原 SSCLEA
// ---------------------------------------------------------------------------
const SSCL_UA =
  '04b038bd3450aff1c985e74918f6aeac37a6c05193c9c68654ab02dad094279177e8d692af475613983366ea67abc310e75b3c1fbe1ae51d4dda1519762f8e1b2e'
const KEY_NAME = 'verify-sscl-插值自洽'
const token = first.token

/** 找一把 sentinel 密钥；没有就创建一把，然后**更新**它（更新走 Java 路径） */
async function ensureUpdatedSsclKey() {
  const list = await api('/generate-api', '/generate/key/list?pageSize=200', { token })
  const rows = list.json?.rows || []
  let key = rows.find((k) => k.keyName === KEY_NAME)

  if (!key) {
    const created = await api('/generate-api', '/generate/keymanage', {
      token,
      method: 'POST',
      body: {
        encrytType: '无证书非对称加密',
        encrytName: 'SSCL',
        keyName: KEY_NAME,
        keyUse: '自动化验收',
        keyDomain: 'A',
        uA: SSCL_UA
      }
    })
    if (created.json?.code !== 200) return { error: `创建失败: ${created.json?.msg}` }
    for (let i = 0; i < 25 && !key; i++) {
      await new Promise((r) => setTimeout(r, 700))
      const again = await api('/generate-api', '/generate/key/list?pageSize=200', { token })
      key = (again.json?.rows || []).find((k) => k.keyName === KEY_NAME)
    }
    if (!key) return { error: '创建后未能在列表中查到' }
  }

  // 更新：带新的 ua，走生命周期侧 Java 生成器（SsclKeyGenerator）
  const updated = await api('/lifecycle-api', '/lifecycle/keymanage', {
    token,
    method: 'PUT',
    body: {
      keyId: key.keyId,
      encrytType: '无证书非对称加密',
      encrytName: 'SSCL',
      keyName: KEY_NAME,
      keyUse: '自动化验收',
      keyDomain: 'A',
      ua: SSCL_UA
    }
  })
  if (updated.json?.code !== 200) return { error: `更新失败: ${updated.json?.msg}`, keyId: key.keyId }

  // 取详情（属主身份 → 材料保留）
  await new Promise((r) => setTimeout(r, 1500))
  const detail = await api('/lifecycle-api', `/lifecycle/keymanage/${key.keyId}`, { token })
  const entity = detail.json?.data
  return { keyId: key.keyId, entity, raw: detail.json }
}

const { keyId, entity, raw, error } = await ensureUpdatedSsclKey()
check('能通过生命周期更新路径生成一份 SSCL 材料（即 Java 侧生成器）', !error, error || `keyId=${keyId}`)

if (!error && entity) {
  const material = entity.key_value ?? entity.keyValue
  let parsed = material
  if (typeof material === 'string') {
    try {
      parsed = JSON.parse(material)
    } catch {
      parsed = null
    }
  }
  check('更新后的密钥带 SSCLKey/SSCLEA（未被脱敏，因为调用方是属主）',
    Boolean(parsed?.SSCLKey && parsed?.SSCLEA),
    `keys=${parsed ? Object.keys(parsed).join(',') : 'n/a'}`)

  if (parsed?.SSCLKey && parsed?.SSCLEA) {
    const share = parsed.SSCLKey
    const mxHex = share.slice(2, 66)
    const myHex = share.slice(66, 130)
    const mx = BigInt('0x' + mxHex)
    const my = BigInt('0x' + myHex)

    const xPoints = [...xs, mx]
    const yPoints = [...first.ys, my]

    let recovered = null
    try {
      recovered = interpolateAtZero(xPoints, yPoints, N)
    } catch (e) {
      check('拉格朗日插值可执行', false, e.message)
    }

    if (recovered !== null) {
      const storedEA = BigInt('0x' + parsed.SSCLEA)
      const asHex = (v) => v.toString(16).padStart(64, '0')
      check(
        '★ 用浏览器插值算法还原出的常数项 == 密钥里存的 SSCLEA',
        recovered === storedEA,
        recovered === storedEA
          ? `SSCLEA=${asHex(storedEA).slice(0, 24)}…`
          : `插值得 ${asHex(recovered).slice(0, 24)}…  期望 ${asHex(storedEA).slice(0, 24)}…`
      )
      console.log(`         （这一条同时覆盖"Go 发布的点"与"Java 生成的材料"是否共线）`)
    }
  }
} else if (error) {
  console.log(`         原始响应: ${JSON.stringify(raw).slice(0, 240)}`)
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('SSCL 域参数一致：发布参数可复现，且客户端能插值还原出存储的 SSCLEA。\n')