#!/usr/bin/env node
/**
 * 节点侧密码能力的验收（文档 §4.4）
 * =============================================================================
 * 验证 `CryptoProvider` / `BrowserCryptoProvider` / `NodeKeyStore` 三件东西。
 *
 * 为什么必须与服务端**对打**，而不是只做本地往返
 * ----------------------------------------------
 * "本地加密→本地解密能还原"这种自洽测试，一个**完全错误**的实现也能通过 ——
 * 它只证明了自己和自己一致。真正要证明的是：
 *
 *   1. 本地密钥库里的私钥**搜不到明文**（这是 §4.4 对存储的硬要求）
 *   2. 本地生成的密钥，**服务端封装后本地能解回**，且共享密钥**逐字节相同**
 *   3. 本地签名，**服务端能验**（反向亦然）
 *
 * 第 2、3 条是唯一能说明"两边真的是同一套算法"的判据。这一条在本项目里
 * 已经踩过两次坑，且**两次都不报错**：
 *   * Kyber 是 ML-KEM 而非 round-3 时，解封只会返回另一个共享密钥，长度格式全对；
 *   * Falcon 的附加签名格式是 `[长度]‖nonce‖消息‖签名` 而非 `sig‖消息`，
 *     拼错只会得到 `crypto_sign_open` 返回 -1（"验签失败"），看不出是格式问题。
 *
 * 用法（必须在前端目录下跑 —— 依赖 front 的 node_modules）
 *     cd kms-updatedel/front && npm run verify:crypto
 *
 * 需要的环境：docker 里有 `dvadmin3-django` 容器（服务端侧用真实 .so 对打）。
 * 缺环境时相关用例会明确失败，而不是静默跳过 —— "没跑"与"跑过了"必须可区分。
 */
import 'fake-indexeddb/auto'
import { execFileSync } from 'node:child_process'
import { writeFileSync, unlinkSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// 规范化 keyRef 的构造只留这一个口子（节点段固定为 probe，与下面 generate 的
// nodeId 一致）：格式再变（段名、大小写、版本位）只改这一行。
// 手写的旧格式（如 `node-XXX-KYBER`）在 store 里查不到时，报错是
// "本机没有这把密钥"，看起来像密钥丢了，其实是引用拼错。
const kref = (algo, kid, v = 1) => `node/probe/${algo}/${kid}/${v}`

const HERE = dirname(fileURLToPath(import.meta.url))

const results = []
const check = (name, pass, detail = '') => {
  results.push({ name, pass, detail })
  console.log(`  ${pass ? '[PASS]' : '[FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}

const toHex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, '0')).join('')
const fromHex = (h) => Uint8Array.from(h.match(/.{2}/g).map((b) => parseInt(b, 16)))

/** 在 Django 容器里跑一段 python（用服务端真实的 .so 对打） */
function runPy(code, tag) {
  const local = join(HERE, `._py_${tag}.py`)
  const remote = `/backend/_verify_${tag}.py`
  writeFileSync(local, code, 'utf8')
  try {
    execFileSync('docker', ['cp', local, `dvadmin3-django:${remote}`], { encoding: 'utf8' })
    return execFileSync('docker', ['exec', 'dvadmin3-django', 'python', remote], {
      encoding: 'utf8',
      env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    })
  } finally {
    try { unlinkSync(local) } catch { /* 忽略 */ }
  }
}

function dockerAvailable() {
  try {
    execFileSync('docker', ['exec', 'dvadmin3-django', 'true'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

const store = await import('../src/utils/crypto/node-key-store.js')
const { cryptoProvider } = await import('../src/utils/crypto/browser-provider.js')
const { sm4EncryptBlock, sm4DecryptBlock, sm4GcmEncrypt, sm4GcmDecrypt } = await import('../src/utils/sm4.js')

// ===========================================================================
// 0. SM4 单分组 —— 国标向量
// ===========================================================================
// 为什么先测这个：GCM 往返一致**证明不了任何事**，一个完全错误的 SM4
// 也能自洽地往返。只有国标向量能钉死"我实现的是 SM4"。
console.log('\n=== 0. SM4 单分组：GB/T 32907-2016 附录 A.1 向量 ===')
{
  const key = fromHex('0123456789abcdeffedcba9876543210')
  const plain = fromHex('0123456789abcdeffedcba9876543210')
  const expected = '681edf34d206965e86b3e94f536e4246'
  const got = toHex(sm4EncryptBlock(key, plain))
  check('★ 单分组加密与国标向量逐字节一致', got === expected, got === expected ? '' : `得到 ${got}`)
  check('单分组解密还原', toHex(sm4DecryptBlock(key, fromHex(expected))) === toHex(plain))
}

// ===========================================================================
// 1. 本地密钥库：明文不得落库
// ===========================================================================
console.log('\n=== 1. 密钥库：私密材料不以明文落库 ===')
const SECRET_HEX = 'deadbeef0123456789abcdef0123456789abcdef0123456789abcdef01234567'
await store.sealSecret(kref('KYBER', 'probe-1'), { algorithm: 'KYBER', secret: SECRET_HEX, publicKey: 'aa'.repeat(16) })

const db = await new Promise((resolve, reject) => {
  const request = indexedDB.open('kms-node-keystore')
  request.onsuccess = () => resolve(request.result)
  request.onerror = () => reject(request.error)
})
const rawRecords = await new Promise((resolve, reject) => {
  const tx = db.transaction('keys', 'readonly')
  const rq = tx.objectStore('keys').getAll()
  rq.onsuccess = () => resolve(rq.result)
  rq.onerror = () => reject(rq.error)
})
// 把整库倒成可搜索的文本 —— 这是"搜不到明文"这条断言的唯一可信做法：
// 只看记录对象上的字段名，会漏掉"明文藏在某个嵌套结构里"的情况。
const dumped = JSON.stringify(
  rawRecords.map((r) => ({
    ...r,
    sealed: r.sealed ? [...new Uint8Array(r.sealed)] : null,
    iv: r.iv ? [...new Uint8Array(r.iv)] : null
  }))
)
check('★ IndexedDB 原始记录里搜不到私钥明文', !dumped.includes(SECRET_HEX), `记录数=${rawRecords.length}`)
check('记录里确实有密文（不是根本没写进去）', (rawRecords[0]?.sealed?.byteLength || 0) > 0,
  `密文长度=${rawRecords[0]?.sealed?.byteLength}`)

const restored = await store.unsealSecret(kref('KYBER', 'probe-1'))
check('取回后逐字节还原', new TextDecoder().decode(restored) === SECRET_HEX)

console.log('\n=== 2. 保护密钥不可导出（防的是"密钥被带走"）===')
check('★ crypto.subtle.exportKey 对保护密钥抛错', await store.assertProtectorNotExportable())
// 说清这条边界的射程：不可导出**不等于**安全。同源 XSS 在页面内仍可调用
// unsealSecret 读到明文 —— 那是纯浏览器方案消除不了的部分，
// 也正是 CryptoProvider 留给 AgentCryptoProvider 的位置。
console.log('  [info] 注意：不可导出只防"密钥被带走"，同源 XSS 仍可在页面内读到明文')

console.log('\n=== 3. 设备标识（设备绑定的基础）===')
const deviceId = await store.getDeviceId()
check('deviceId 持久且稳定', deviceId && deviceId === (await store.getDeviceId()))
check('记录带上了 deviceId', rawRecords[0]?.deviceId === deviceId)

console.log('\n=== 4. 失败要明确，不能返回空 ===')
let threw = false
try { await store.unsealSecret(kref('KYBER', 'never-created')) } catch { threw = true }
check('取不存在的引用抛错（而非返回空 buffer）', threw)

// ===========================================================================
// 5. 与服务端对打
// ===========================================================================
console.log('\n=== 5. Kyber：本地生成 → 服务端封装 → 本地解封 ===')
if (!dockerAvailable()) {
  check('★★ 服务端对打（Kyber）', false, 'docker 容器 dvadmin3-django 不可用 —— 该项未运行')
} else {
  const kb = await cryptoProvider.generate('KYBER', { nodeId: 'probe', keyId: 'probe-kyber', variant: 768 })
  check('公钥长度正确（Kyber-768 = 1184B）', kb.publicKey.length === 2368, `${kb.publicKey.length} hex 字符`)

  const out = runPy(`
import os, django, binascii
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings")
django.setup()
from pqkds.crypto_utils import KyberCrypto
pk = binascii.unhexlify("${kb.publicKey}")
ct, ss = KyberCrypto(768).encrypt(pk)
print("CT:", binascii.hexlify(ct).decode())
print("SS:", binascii.hexlify(ss).decode())
`, 'kyber')

  const ctHex = (out.match(/CT:\s*([0-9a-f]+)/) || [])[1]
  const ssServer = (out.match(/SS:\s*([0-9a-f]+)/) || [])[1]
  if (!ctHex) {
    check('★★ 服务端接受该公钥并封装', false, out.trim().slice(0, 140))
  } else {
    check('服务端接受该公钥并封装', true)
    const ssLocal = toHex(await cryptoProvider.decapsulate('KYBER', kb.keyRef, fromHex(ctHex)))
    check('★★ 共享密钥逐字节相同', ssLocal === ssServer,
      ssLocal === ssServer ? '' : `本地=${ssLocal.slice(0, 16)}… 服务端=${ssServer.slice(0, 16)}…`)
  }
}

console.log('\n=== 6. Falcon：本地签名 → 服务端验签 ===')
// fb 提到 if 之外：§8 的 hasKey 要验的正是这里生成的那把。
// 用返回值里的 keyRef 而不是再手写一个 —— 手写串与 store 对不上时，
// hasKey 只会返回 false，看起来像"密钥没生成"，实际是引用拼错。
let fb = null
if (!dockerAvailable()) {
  check('★★ 服务端对打（Falcon）', false, 'docker 容器 dvadmin3-django 不可用 —— 该项未运行')
} else {
  fb = await cryptoProvider.generate('FALCON', { nodeId: 'probe', keyId: 'probe-falcon' })
  check('公钥长度正确（Falcon-512 = 897B）', fb.publicKey.length === 1794, `${fb.publicKey.length} hex 字符`)

  const msg = new TextEncoder().encode('verify-node-crypto ' + Date.now())
  const sig = await cryptoProvider.sign('FALCON', fb.keyRef, msg)
  check('签名产出附加格式（长度 > 消息）', sig.length > msg.length, `${sig.length}B`)

  const out = runPy(`
import ctypes, binascii
u8 = ctypes.c_ubyte
lib = ctypes.CDLL("/backend/falcon/falcon512/falcon512int/falcon512.dll")
pk = binascii.unhexlify("${fb.publicKey}")
sm = binascii.unhexlify("${toHex(sig)}")
out = (u8 * len(sm))()
outlen = ctypes.c_ulonglong()
r = lib.crypto_sign_open(out, ctypes.byref(outlen), (u8 * len(sm)).from_buffer_copy(sm),
                         ctypes.c_ulonglong(len(sm)), (u8 * len(pk)).from_buffer_copy(pk))
print("RET:", r)
print("MSG:", binascii.hexlify(bytes(out[:outlen.value])).decode() if r == 0 else "")
`, 'falcon')

  check('★★ 服务端接受本地签名（crypto_sign_open 返回 0）', /RET:\s*0/.test(out),
    /RET:\s*0/.test(out) ? '' : out.trim().slice(0, 100))
  const recovered = (out.match(/MSG:\s*([0-9a-f]*)/) || [])[1]
  check('恢复出的消息与原文一致', recovered === toHex(msg))
}

console.log('\n=== 7. 本地 verify 不能只是"结构合法" ===')
{
  const fb = await cryptoProvider.generate('FALCON', { nodeId: 'probe', keyId: 'probe-verify' })
  const msg = new TextEncoder().encode('probe-verify ' + Date.now())
  const sig = await cryptoProvider.sign('FALCON', fb.keyRef, msg)
  check('正确消息验签通过', (await cryptoProvider.verify('FALCON', fb.publicKey, sig, msg)) === true)
  // 若篡改后仍"验签通过"，说明 verify 只检查了结构而没绑消息 —— 等于没验。
  check('★ 篡改消息验签失败', (await cryptoProvider.verify('FALCON', fb.publicKey, sig, new TextEncoder().encode('tampered'))) === false)
}

console.log('\n=== 8. 设备绑定的判断基础 ===')
check('本地持有刚生成的密钥', fb !== null && (await cryptoProvider.hasKey(fb.keyRef)))
check('本地不持有的引用返回 false（新设备即此情形）', (await cryptoProvider.hasKey(kref('KYBER', 'never-created'))) === false)

console.log('\n=== 9. SM4-GCM 与服务端 pycryptodome 双向互通 ===')
if (!dockerAvailable()) {
  check('★★ SM4-GCM 互通', false, 'docker 容器 dvadmin3-django 不可用 —— 该项未运行')
} else {
  const key = fromHex('0123456789abcdeffedcba9876543210')
  const iv = fromHex('00112233445566778899aabb')
  const aad = new TextEncoder().encode('kms-envelope-aad')
  const pt = new TextEncoder().encode('SM4 session key material 16B')

  // 服务端加密 → 本地解密
  const out = runPy(`
import binascii
from pqkds.sm4_crypto import SM4Crypto
ct, nt = SM4Crypto.encrypt(
    binascii.unhexlify("${toHex(pt)}"),
    binascii.unhexlify("${toHex(key)}"),
    binascii.unhexlify("${toHex(aad)}"))
print("CT:", binascii.hexlify(ct).decode())
print("NT:", binascii.hexlify(nt).decode())
`, 'sm4')
  const ctHex = (out.match(/CT:\s*([0-9a-f]+)/) || [])[1]
  const ntHex = (out.match(/NT:\s*([0-9a-f]+)/) || [])[1]
  if (!ctHex) {
    check('服务端 SM4-GCM 加密', false, out.trim().slice(0, 140))
  } else {
    const nt = fromHex(ntHex)
    let ok = false
    let err = ''
    // 服务端约定 nonceTag = iv(12) ‖ tag(16)（sm4_crypto.py:150-152）
    try { ok = toHex(sm4GcmDecrypt(key, fromHex(ctHex), nt.slice(0, 12), nt.slice(12), aad)) === toHex(pt) } catch (e) { err = e.message }
    check('★★ 本地解开服务端的 SM4-GCM 密文', ok, ok ? '' : err)
  }

  // 本地加密 → 服务端解密
  const { ciphertext, tag } = sm4GcmEncrypt(key, pt, iv, aad)
  const out2 = runPy(`
import binascii
from pqkds.sm4_crypto import SM4Crypto
try:
    got = SM4Crypto.decrypt(
        binascii.unhexlify("${toHex(ciphertext)}"),
        binascii.unhexlify("${toHex(key)}"),
        binascii.unhexlify("${toHex(iv)}") + binascii.unhexlify("${toHex(tag)}"),
        binascii.unhexlify("${toHex(aad)}"))
    print("OK:", binascii.hexlify(got).decode())
except Exception as e:
    print("ERR:", e)
`, 'sm4b')
  const okHex = (out2.match(/OK:\s*([0-9a-f]+)/) || [])[1]
  check('★★ 服务端解开本地的 SM4-GCM 密文', okHex === toHex(pt), okHex === toHex(pt) ? '' : out2.trim().slice(0, 120))
}

console.log('\n=== 10. GCM 的认证标签必须真的被校验 ===')
{
  const key = fromHex('00112233445566778899aabbccddeeff')
  const iv = fromHex('00112233445566778899aabb')
  const pt = new TextEncoder().encode('auth-tag-check')
  const { ciphertext, tag } = sm4GcmEncrypt(key, pt, iv)
  const bad = Uint8Array.from(tag)
  bad[0] ^= 1
  let threw = false
  try { sm4GcmDecrypt(key, ciphertext, iv, bad) } catch { threw = true }
  // 不验 tag 就返回，等于把可被随意篡改的密文当成可信数据 ——
  // 而且解出来的"明文"长度完全正常，调用方看不出异常。
  check('★ 篡改 tag 后抛错（而不是返回乱码）', threw)
}

// ===========================================================================
const pass = results.filter((r) => r.pass).length
console.log(`\n=== 结果：${pass}/${results.length} 项通过 ===`)
if (pass !== results.length) {
  results.filter((r) => !r.pass).forEach((r) => console.log(`  - ${r.name}  ${r.detail}`))
  process.exitCode = 1
}