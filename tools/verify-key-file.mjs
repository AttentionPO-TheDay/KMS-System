#!/usr/bin/env node
/**
 * 用户密钥文件（导出/导入）的自测 —— 计划 §7 P3 步骤 0b
 * =============================================================================
 * 密钥文件是用户**唯一**的 `d_a` 副本。它一旦校验失效却仍被拿来解密，
 * 现象只会是"解不开"，而用户无从知道是自己导错了文件。
 * 所以这里的重点是**校验必须能咬人**：每一种破坏都要被明确拒绝。
 *
 * 它直接 import 前端的 `key-file.js`（该模块没有别名依赖，Node 能直接加载），
 * 因此测的就是真正跑在浏览器里的那份代码，不是复制品。
 *
 * 用法：node tools/verify-key-file.mjs
 * =============================================================================
 */

const MODULE_PATH = new URL('../kms-user/front/src/utils/key-file.js', import.meta.url).href
const { buildKeyFile, parseKeyFile, serializeKeyFile, computeChecksum, suggestFileName, KEY_FILE_VERSION } =
  await import(MODULE_PATH)

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

/** 断言某个操作**必须**抛出，且错误信息里含关键提示 */
async function expectThrow(name, fn, keyword = '') {
  try {
    await fn()
  } catch (error) {
    const ok = !keyword || String(error.message).includes(keyword)
    check(name, ok, ok ? '' : `错误信息缺少"${keyword}"：${error.message}`)
    return
  }
  check(name, false, '竟然没有报错')
}

const SAMPLES = {
  privateShare: 'a'.repeat(63) + '1',
  publicKey: '04' + 'b'.repeat(128)
}

async function buildSample(overrides = {}) {
  return buildKeyFile({
    keyId: 23,
    userId: 2,
    algorithm: 'SM2',
    privateShare: SAMPLES.privateShare,
    publicKey: SAMPLES.publicKey,
    ...overrides
  })
}

console.log('\n=== 用户密钥文件自测 ===\n')

// ---------------------------------------------------------------------------
console.log('1. 生成与往返')
{
  const file = await buildSample()
  check('生成的文件带 version/kind/checksum',
    file.version === KEY_FILE_VERSION && file.kind === 'kms-user-key' && String(file.checksum).startsWith('sha256:'),
    `version=${file.version}`)
  check('checksum 是 64 位十六进制摘要',
    /^sha256:[0-9a-f]{64}$/.test(file.checksum))

  const text = serializeKeyFile(file)
  const parsed = await parseKeyFile(text)
  check('导出 → 解析往返成功', parsed.key_id === '23' && parsed.private_share === SAMPLES.privateShare)
  check('解析结果保留算法与公钥', parsed.algorithm === 'SM2' && parsed.public_key === SAMPLES.publicKey)

  const name = suggestFileName(file)
  check('建议文件名含 key_id 与算法', name.includes('23') && name.includes('SM2'), name)
}

// ---------------------------------------------------------------------------
console.log('\n2. 校验必须能咬人（每一种破坏都要被拒绝）')
{
  const file = await buildSample()

  // 改私钥份额 —— 最危险的一种：文件仍然"结构完整"，但私钥被换了
  const tamperedShare = { ...file, private_share: 'c'.repeat(64) }
  await expectThrow('篡改 private_share → 校验和失配', () => parseKeyFile(tamperedShare), '校验和不匹配')

  const tamperedKeyId = { ...file, key_id: '99' }
  await expectThrow('篡改 key_id → 校验和失配', () => parseKeyFile(tamperedKeyId), '校验和不匹配')

  const tamperedUser = { ...file, user_id: '1' }
  await expectThrow('篡改 user_id → 校验和失配', () => parseKeyFile(tamperedUser), '校验和不匹配')

  await expectThrow('缺少 checksum → 拒绝', () => {
    const { checksum, ...rest } = file
    void checksum
    return parseKeyFile(rest)
  }, '缺少校验和')

  await expectThrow('截断的 JSON → 拒绝', () => parseKeyFile('{"version":1,"kind":"kms-user-key"'), '不是合法 JSON')
  await expectThrow('空内容 → 拒绝', () => parseKeyFile(''), '不是合法 JSON')
  await expectThrow('kind 不对 → 拒绝', () => parseKeyFile({ ...file, kind: 'something-else' }), '不是本系统的密钥文件')
  await expectThrow('版本不支持 → 拒绝', () => parseKeyFile({ ...file, version: 99 }), '版本不支持')

  // 校验和过了但字段格式非法（例如有人手工重算了校验和却填了短私钥）
  const badShare = { version: 1, kind: 'kms-user-key', key_id: '23', user_id: '2', algorithm: 'SM2', created_at: file.created_at, private_share: 'abc', public_key: '' }
  const withChecksum = { ...badShare, checksum: await computeChecksum(badShare) }
  await expectThrow('校验和正确但 private_share 格式非法 → 仍拒绝', () => parseKeyFile(withChecksum), 'private_share 格式非法')
}

// ---------------------------------------------------------------------------
console.log('\n3. 关键性质：字段顺序/缩进不影响校验（规范化生效）')
{
  const file = await buildSample()
  // 打乱字段顺序 + 重新缩进，内容不变 → 必须仍然校验通过
  const shuffled = {}
  for (const key of Object.keys(file).reverse()) {
    shuffled[key] = file[key]
  }
  const reparsed = await parseKeyFile(JSON.stringify(shuffled, null, 4))
  check('字段顺序被打乱 + 缩进变化 → 仍能通过校验（说明校验的是内容而非文本）',
    reparsed.key_id === '23')

  // 但多出无关字段不应影响校验（日后再加字段不会让旧文件失效）
  const withExtra = { ...file, note: '用户自己加的备注' }
  const reparsedExtra = await parseKeyFile(withExtra)
  check('多出无关字段 → 仍能通过校验（为日后扩展留余地）', reparsedExtra.key_id === '23')
}

// ---------------------------------------------------------------------------
console.log('\n4. 入参校验')
{
  await expectThrow('缺少 key_id → 拒绝（否则文件对应不回记录）',
    () => buildKeyFile({ userId: 2, algorithm: 'SM2', privateShare: SAMPLES.privateShare }), '缺少 key_id')
  await expectThrow('缺少 user_id → 拒绝',
    () => buildKeyFile({ keyId: 1, algorithm: 'SM2', privateShare: SAMPLES.privateShare }), '缺少 user_id')
  await expectThrow('私钥份额长度不对 → 拒绝',
    () => buildKeyFile({ keyId: 1, userId: 2, algorithm: 'SM2', privateShare: 'abcd' }), '格式非法')
  await expectThrow('公钥不是 04 开头的 130 位 → 拒绝',
    () => buildKeyFile({ keyId: 1, userId: 2, algorithm: 'SM2', privateShare: SAMPLES.privateShare, publicKey: 'deadbeef' }), '格式非法')

  const noPublic = await buildSample({ publicKey: '' })
  check('公钥可以不填（留空则跳过公钥格式校验）', noPublic.public_key === '')
  const reparsed = await parseKeyFile(noPublic)
  check('无公钥的文件仍可导入', reparsed.public_key === '')
}

console.log(`\n=== 结果：${pass} 通过 / ${fail} 失败 ===`)
if (fail) {
  console.log('失败项：')
  failures.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('密钥文件格式与校验行为符合预期。\n')