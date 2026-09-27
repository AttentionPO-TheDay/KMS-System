#!/usr/bin/env node
/**
 * 浏览器侧 SM3 / SM2 解密的验收（P3 收尾）
 * =============================================================================
 * 这是"用户能不能在本机解开信封"的最后一块。它交付的是**自己写的密码学代码**，
 * 所以不能只测"往返一致" —— 自洽但错误的实现也能往返一致。
 *
 * 这里用**国标原文的标准向量**钉死：
 *
 *   SM3（GB/T 32905-2016 附录 A）
 *     SM3("abc")        = 66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0
 *     SM3("abcd" × 16)  = debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732
 *
 *   SM2（GB/T 32918.4-2016 附录 A.2 示例2）—— 用它公布的密文反解出原文
 *     d_B = 1649AB77A00637BD5E2EFE283FBF353534AA7F7CB89463F208DDBC2920BB0DA0
 *     C   = C1 || C3 || C2（附录原文的字节串）
 *     M   = "encryption standard"
 *
 *   ⚠️ 该示例跑在**附录自己的测试曲线**上（p = 8542D69E…），**不是生产的 sm2p256v1**
 *      （p = FFFFFFFE…）。所以曲线参数是可注入的，测试注入附录曲线。
 *      直接用生产曲线去解会失败 —— 这是最容易踩的坑。
 *
 * 结论的含义：SM2 那条断言**逐字节对齐国标原文**，因此它能证明实现是对的，
 * 而不只是自洽。
 *
 * 用法：node tools/verify-sm3-sm2-js.mjs
 * =============================================================================
 */

const sm3Mod = await import(new URL('../kms-user/front/src/utils/sm3.js', import.meta.url).href)
const sm2Mod = await import(new URL('../kms-user/front/src/utils/sm2-envelope.js', import.meta.url).href)

const { sm3, bytesToHex, hexToBytes } = sm3Mod
const { decryptEnvelope, decryptToHex, isValidPublicKey, Sm2IntegrityError, SM2_P256 } = sm2Mod

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
const utf8 = (s) => new TextEncoder().encode(s)

console.log('\n=== 浏览器侧 SM3 / SM2 验收 ===\n')

// ---------------------------------------------------------------------------
console.log('1. SM3 国标向量（GB/T 32905-2016 附录 A）')
{
  const abc = bytesToHex(sm3(utf8('abc')))
  check('SM3("abc") 与国标一致',
    abc === '66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0',
    abc)

  const abcd16 = bytesToHex(sm3(utf8('abcd'.repeat(16))))
  check('SM3("abcd"×16) 与国标一致（覆盖多分组与填充边界）',
    abcd16 === 'debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732',
    abcd16)

  // 空串：不是国标向量，但能覆盖"只有填充块"这一条边界
  const empty = bytesToHex(sm3(new Uint8Array(0)))
  check('空输入能算出结果且长度正确（边界）', /^[0-9a-f]{64}$/.test(empty), empty.slice(0, 16) + '…')

  // 分组边界：55/56/64/65 字节决定填充落在哪一块，是最容易写错的地方
  const sizes = [55, 56, 63, 64, 65, 119, 120, 128]
  const digests = sizes.map((n) => bytesToHex(sm3(new Uint8Array(n).fill(0x61))))
  check('所有分组边界长度都能算出结果', digests.every((d) => /^[0-9a-f]{64}$/.test(d)),
    `覆盖 ${sizes.join('/')} 字节`)
  check('不同长度得到不同摘要（填充没有吃掉数据）', new Set(digests).size === digests.length)
}

// ---------------------------------------------------------------------------
console.log('\n2. SM2 国标向量：用它公布的密文反解出原文')
{
  // GB/T 32918.4-2016 附录 A.2 示例2 的**测试曲线**
  const GB_CURVE = {
    name: 'gb-appendix-a2',
    p: BigInt('0x8542D69E4C044F18E8B92435BF6FF7DE457283915C45517D722EDB8B08F1DFC3'),
    a: BigInt('0x787968B4FA32C3FD2417842E73BBFEFF2F3C848B6831D7E0EC65228B3937E498'),
    b: BigInt('0x63E4C6D3B23B0C849CF84241484BFE48F61D59A5B16BA06E6E12D1DA27C5249A'),
    n: BigInt('0x8542D69E4C044F18E8B92435BF6FF7DD297720630485628D5AE74EE7C32E79B7'),
    gx: BigInt('0x421DEBD61B62EAB6746434EBC3CC315E32220B3BADD50BDC4C4E6C147FEDD43D'),
    gy: BigInt('0x0680512BCBB42C07D47349D2153B70C4E5D7FDFCBFA36EA1A85841B9E46E09A2')
  }
  const GB_DB = '1649AB77A00637BD5E2EFE283FBF353534AA7F7CB89463F208DDBC2920BB0DA0'
  const GB_C1 = '04245C26FB68B1DDDDB12C4B6BF9F2B6D5FE60A383B0D18D1C4144ABF17F6252E776CB9264C2A7E88E52B19903FDC47378F605E36811F5C07423A24B84400F01B8'
  const GB_C3 = '9C3D7360C30156FAB7C80A0276712DA9D8094A634B766D3A285E07480653426D'
  const GB_C2 = '650053A89B41C418B0C3AAD00D886C00286467'
  const GB_M = 'encryption standard'

  const envelope = {
    algorithm: 'sm2',
    ciphertext: (GB_C1 + GB_C3 + GB_C2).toLowerCase(),
    public_key: ''
  }

  let plain = null
  try {
    plain = decryptEnvelope(envelope, GB_DB, GB_CURVE)
  } catch (error) {
    check('★ 用国标附录密文反解出原文', false, `${error.name}: ${error.message}`)
  }
  if (plain) {
    const text = new TextDecoder().decode(plain)
    check('★ 解出的明文逐字节等于国标原文 "encryption standard"',
      text === GB_M, `得到 "${text}"`)
    check('明文长度与国标一致（19 字节）', plain.length === 19, `${plain.length} 字节`)
  }

  // 附录的 C1 在**生产曲线**上不是合法点 —— 这直接证明了曲线参数必须可注入，
  // 也顺带说明"拿生产曲线去跑国标向量"是个真实的坑。
  check('国标附录的 C1 在 sm2p256v1 上**不是**合法点（故曲线必须可注入）',
    !isValidPublicKey(GB_C1.toLowerCase(), SM2_P256))
  check('而它在附录自己的曲线上是合法点',
    isValidPublicKey(GB_C1.toLowerCase(), GB_CURVE))

  let wrongCurveFailed = false
  try {
    decryptEnvelope(envelope, GB_DB, SM2_P256)
  } catch {
    wrongCurveFailed = true
  }
  check('用生产曲线解国标密文会失败（不会静默给出垃圾）', wrongCurveFailed)
}

// ---------------------------------------------------------------------------
console.log('\n3. 生产曲线上的往返与失败路径')
{
  // 造一对密钥：d 随机，P = d·G 用模块自己的点运算算（借道 isValidPublicKey 的曲线校验）
  // 这里直接用一个固定标量，避免在测试里再写一份点乘
  const d = BigInt('0x' + '11'.repeat(32))
  // 通过服务端已验证的实现生成 P 不现实（跨语言），因此往返测试用"已知密文"方式：
  // 见第 4 节（读服务端真实信封）。这里先测**输入校验**这些不依赖点乘的路径。
  check('拒绝非对象信封', (() => { try { decryptEnvelope(null, '11'.repeat(32)); return false } catch { return true } })())
  check('拒绝算法标记不是 sm2 的信封',
    (() => { try { decryptEnvelope({ algorithm: 'sm4', ciphertext: 'aa'.repeat(100) }, '11'.repeat(32)); return false } catch (e) { return /不是 sm2/.test(e.message) } })())
  check('拒绝过短的密文',
    (() => { try { decryptEnvelope({ algorithm: 'sm2', ciphertext: 'aabb' }, '11'.repeat(32)); return false } catch (e) { return /长度不足/.test(e.message) } })())
  check('拒绝长度不对的私钥',
    (() => { try { decryptEnvelope({ algorithm: 'sm2', ciphertext: 'aa'.repeat(100) }, 'abcd'); return false } catch (e) { return /64 位十六进制/.test(e.message) } })())
  check('拒绝越界的私钥（0）',
    (() => { try { decryptEnvelope({ algorithm: 'sm2', ciphertext: 'aa'.repeat(100) }, '00'.repeat(32)); return false } catch (e) { return /范围内/.test(e.message) } })())

  // 不在曲线上的 C1 必须被明确拒绝，而不是算出一堆垃圾
  const offCurve = '04' + '11'.repeat(64)
  check('拒绝不在曲线上的 C1',
    (() => { try { decryptEnvelope({ algorithm: 'sm2', ciphertext: offCurve + 'aa'.repeat(48) }, '11'.repeat(32)); return false } catch (e) { return /不在曲线上/.test(e.message) } })())
}

// ---------------------------------------------------------------------------
console.log('\n4. ★ 与服务端互通：解开服务端真实封出的信封')
{
  // 由 tools/verify-sm3-sm2-js.mjs 的调用方（shell）把服务端产出的
  // 「私钥 + 信封 + 期望明文」以 JSON 放到临时文件里传进来；
  // 没传就跳过 —— 但**跳过要明说**，不能悄悄算过。
  const fs = await import('node:fs')
  const path = process.env.SM2_INTEROP_JSON
  if (!path || !fs.existsSync(path)) {
    console.log('  [SKIP] 未提供服务端互通样本（设 SM2_INTEROP_JSON=<文件> 后再跑）')
  } else {
    const sample = JSON.parse(fs.readFileSync(path, 'utf8'))
    const hex = decryptToHex(sample.envelope, sample.privateKey)
    check('★ 用浏览器侧实现解开**服务端真实封出**的信封',
      hex === sample.expectedKeyHex,
      hex === sample.expectedKeyHex ? `${hex.slice(0, 16)}…` : `得到 ${hex.slice(0, 24)}… 期望 ${sample.expectedKeyHex.slice(0, 24)}…`)

    // 篡改后必须报完整性错误
    const tampered = JSON.parse(JSON.stringify(sample.envelope))
    const ct = tampered.ciphertext
    tampered.ciphertext = ct.slice(0, -2) + (ct.slice(-2) === '00' ? '11' : '00')
    let caught = null
    try { decryptEnvelope(tampered, sample.privateKey) } catch (e) { caught = e }
    check('★ 篡改密文后报完整性错误（而非返回垃圾）', caught instanceof Sm2IntegrityError,
      caught ? caught.name : '竟然没报错')

    // 换一把私钥必须失败
    let wrongKey = null
    try { decryptEnvelope(sample.envelope, '22'.repeat(32)) } catch (e) { wrongKey = e }
    check('★ 换一把私钥解不开', wrongKey instanceof Sm2IntegrityError, wrongKey ? wrongKey.name : '竟然解开了')
  }
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('SM3 通过国标向量；SM2 能逐字节解出国标附录密文。\n')