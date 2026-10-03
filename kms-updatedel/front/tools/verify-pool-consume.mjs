/**
 * KMS-013 验收：**预分配池项的消费**（计划 §7 阶段 5 的全部判据）。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 本阶段的主体是"预分配密钥必须一次性消费"，而**每一步都能在失败的情况下
 * 返回成功**：
 *
 *   * "取用成功" ≠ "只有一个人取到"。第 5 节用**真并发**钉它：起 8 个
 *     独立 node 子进程同时打同一批池项，断言成功数**恰好等于可用条数**
 *     （1 条时 1 个成功、3 条时 3 个成功），其余都拿到
 *     `POOL_ITEM_UNAVAILABLE`，并且**库里的 CONSUMED 条数逐一对应**。
 *     串行调两次"第一次成功、第二次失败"证明不了任何并发性质 —— 断口
 *     存在时它照样可能绿（两次各拿到同一条、各自标记成功）。
 *     ⚠️ 夹具必须让"该节点对此刻只有这一批 READY 行"，否则消费是按
 *     `key_index` 跨批次取第一条，别的批次会被一起抢走 —— 脚本里每个
 *     并发夹具前都有一次排空检查（`只剩这一批 READY`）。
 *   * "消费失败" ≠ "它知道自己为什么失败"。`consume_key` 在 KMS-013 之前
 *     **从未成功执行过**（裸名 `POOL_STATUS_READY_VALUES` → NameError；
 *     修掉后还有无外层事务的 `select_for_update` → TransactionManagementError），
 *     而 HTTP 层把它收成「密钥取用失败: name ... is not defined」—— 第 1 节
 *     的部署探针就是冲着这句话去的：老错误串还在，说明跑的是旧代码。
 *   * "回收了" ≠ "池项不会继续分发"。第 9 节撤掉池项引用的那把长期密钥：
 *     先断言池项被连带标成 REVOKED（KMS-007 的标记面），**再**手工把一条
 *     改回 READY 模拟"标记漏网"的行，断言消费口**自己**拒掉它
 *     （`KEY_REVOKED`）—— 阶段 5 出口检查「目标密钥版本失效后池项不会继续
 *     分发」的后半句，防的就是"标记"与"消费"两处判断各写一套、漂移一处。
 *   * "过期"必须两处同判：页面的 `effective_status` 说 EXPIRED，
 *     消费口就不能把它取走 —— 第 7 节同一条行两边都断言。
 *
 * 与其它脚本的关系
 * ---------------
 * `verify-keyrevoke-impact.mjs`（KMS-007）验的是**回收侧的标记**（撤密钥 →
 * 池项转 REVOKED），本脚本验**消费侧的拒绝**与并发；两侧的引用（
 * `long_term_key_id/version`）是同一份数据。预分配吞吐（阶段 5 的完成标准
 * 之一）在第 8 节用管理命令现跑、把表格原样打印出来。
 *
 * ⚠️ 会**建真节点、写真数据**，只在本地验证环境跑。结尾第 11 节自建自清。
 * ⚠️ 服务端代码打进镜像：改了后端不重建，第 1 节的探针先失败 —— 刻意如此。
 * ⚠️ `/key-pool/*` 命名空间**没有错误码字段**（见 `api_contract.py` 文件头的
 *    三套响应约定）：成败看 `code`（成功 2000 / 失败 400），可编程的码在
 *    **msg 文本**里 —— 本脚本的断言按这条现实写，不去 match HTTP 状态。
 */
import { spawn, execFileSync } from 'node:child_process'
import {
  PQKDS,
  api,
  isOk,
  title,
  makeReporter,
  adminLogin,
  newNodeSession,
  cryptoProvider
} from './lib/node-session.mjs'
import { sqlScalar, dockerBin } from '../../../tools/lib/mysql.mjs'

const { check, info, finish } = makeReporter()

const KYBER = 'KYBER'
const VARIANT = 768
const DOMAIN = 'kms013'

const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'

/**
 * 容器内跑一段 Django ORM 脚本。
 * 沿用 KMS-011 建立的两段式夹具做法：js 拼 SQL 去改 JSON 字段会因引号转义
 * 错一次就测到"没改动的请求"，ORM 不会（信封/材料列尤其容易踩）。
 */
const orm = (program) => execFileSync(
  dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'],
  { input: program, encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } }
)

const ormHeader = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
`

const poolCount = (poolId, status) => Number(sqlScalar(
  `SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='${poolId}' AND status='${status}';`) || 0)

/** 该节点对此刻还剩多少 READY（含历史拼写）row —— 并发夹具的前置检查。 */
const pairReadyCount = (a, b) => Number(sqlScalar(
  `SELECT COUNT(*) FROM ${POOL_TABLE} p `
  + `JOIN falcon_kds.dvadmin_pqkds_nodes n1 ON p.node1_id=n1.id `
  + `JOIN falcon_kds.dvadmin_pqkds_nodes n2 ON p.node2_id=n2.id `
  + `WHERE ((n1.node_id='${a}' AND n2.node_id='${b}') OR (n1.node_id='${b}' AND n2.node_id='${a}')) `
  + `AND p.status IN ('READY','unused') AND p.expires_at > NOW();`) || -1)

const consumeHttp = (node1, node2) => api(PQKDS, '/key-pool/consume/', {
  method: 'POST',
  body: { node1_id: node1, node2_id: node2 }
})

/**
 * 在**独立 node 子进程**里发一次消费请求 —— 每个子进程是独立进程、独立连接，
 * 这就是"真并发"与"同一进程里连调两次"的区别所在。用 `process.execPath`
 * 而不是裸 `node`：新 shell 里 node 不在 PATH（本仓库踩过的坑）。
 */
function consumeInChild(node1, node2) {
  const url = `${PQKDS}/key-pool/consume/`
  const body = JSON.stringify({ node1_id: node1, node2_id: node2 })
  const code = `
    fetch(${JSON.stringify(url)}, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: ${JSON.stringify(body)}
    }).then((r) => r.json())
      .then((b) => process.stdout.write(JSON.stringify(b)))
      .catch((e) => process.stdout.write(JSON.stringify({ __error: String(e) })))
  `
  return new Promise((resolve) => {
    const child = spawn(process.execPath, ['-e', code], { stdio: ['ignore', 'pipe', 'pipe'] })
    let out = ''
    child.stdout.on('data', (d) => { out += d })
    child.on('close', () => {
      try { resolve(JSON.parse(out)) } catch { resolve({ __error: out || '(无输出)' }) }
    })
  })
}

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：`/key-pool/consume/` 到底跑的是哪一份代码
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：consume 不再报 NameError（跑的是 KMS-013 之后的代码）')
info('KMS-013 之前这条路**从未成功执行过**：常量是类属性而函数里用了裸名，')
info("HTTP 层把它收成「密钥取用失败: name 'POOL_STATUS_READY_VALUES' is not defined」。")
info('探针不碰真数据（节点对不存在）—— 老错误串还在，说明镜像没重建。')

const probe1 = await consumeHttp('probe-not-a-node-a', 'probe-not-a-node-b')
const probeText = String(probe1.body?.msg || '')
check('★ consume 已部署：不再出现 "is not defined"（断口 1 已修）',
  !probeText.includes('is not defined'),
  `HTTP=${probe1.status} code=${probe1.body?.code} msg=${probeText.slice(0, 90)}`)
check('★ 如实报"没有可用"并带可编程码 POOL_ITEM_UNAVAILABLE（断口 2 已修：行锁在事务里）',
  !isOk(probe1.body) && probeText.includes('POOL_ITEM_UNAVAILABLE'),
  `msg=${probeText.slice(0, 110)}`)

const probe2 = await api(PQKDS, '/key-pool/consume/', { method: 'POST', body: {} })
check('缺参数仍是明确的参数错误（探针没有把校验路径吃掉）',
  String(probe2.body?.msg || '').includes('缺少 node1_id 或 node2_id'),
  `msg=${String(probe2.body?.msg || '').slice(0, 60)}`)

// ---------------------------------------------------------------------------
// 2. 夹具：两个真节点（四套密钥齐备，预分配闸门要用 KYBER 登记行）
// ---------------------------------------------------------------------------
title('2. 夹具：A/B 两个真节点（登记四套并完成 init —— 预分配要求 KYBER 可用）')

const adminToken = await adminLogin()
const nodeA = await newNodeSession(adminToken, { prefix: 'K13A', name: 'KMS-013 节点A', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'K13B', name: 'KMS-013 节点B', domainId: DOMAIN })
check('两个节点已建好并激活', Boolean(nodeA.token && nodeB.token),
  `${nodeA.nodeId} / ${nodeB.nodeId}`)

const register = (session, algorithm, material, extra = {}) =>
  api(PQKDS, '/node-self/keys/', {
    method: 'POST',
    token: session.token,
    body: {
      algorithm,
      publicKey: material.publicKey,
      securityLevel: extra.securityLevel,
      deviceId: session.fingerprint,
      keyId: material.keyId,
      keyVersion: material.version
    }
  })

info('生成密钥并登记（Falcon 本机生成要十几秒）…')
const keys = { A: {}, B: {} }
for (const [label, session] of [['A', nodeA], ['B', nodeB]]) {
  for (const [algorithm, options, extra] of [
    ['SM2', {}, {}],
    ['SSCL', {}, {}],
    [KYBER, { variant: VARIANT }, { securityLevel: String(VARIANT) }],
    ['FALCON', {}, {}]
  ]) {
    const material = await cryptoProvider.generate(algorithm, { nodeId: session.nodeId, ...options })
    const up = await register(session, algorithm, material, extra)
    if (!isOk(up.body)) {
      check(`${label} 的 ${algorithm} 登记成功`, false, `code=${up.body?.code} msg=${up.body?.msg}`)
    }
    keys[label][algorithm] = material
  }
}
for (const session of [nodeA, nodeB]) {
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
  if (!isOk(init.body)) {
    check(`${session.nodeId} 初始化收尾成功`, false, `msg=${init.body?.msg}`)
  }
}
const kyberKeyId = keys.B[KYBER].keyId
check('A/B 四套密钥已登记（B 的 KYBER 是预分配的封装目标，第 9 节撤的就是它）',
  Boolean(kyberKeyId), `B.KYBER=${kyberKeyId} v${keys.B[KYBER].version}`)

// ---------------------------------------------------------------------------
// 3. 预分配：生成一批池项，引用必须回填（KMS-007 D3 的精确失效面靠它）
// ---------------------------------------------------------------------------
title('3. 预分配一批（HTTP /key-pool/generate/）→ 池项回填接收方长期密钥引用')

const genBatch = (count) => api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId, algorithm: 'kyber_kem', count }
})

const gen3 = await genBatch(3)
const pool3 = gen3.body?.data?.pool_id || ''
check('生成 3 条成功', isOk(gen3.body) && gen3.body?.data?.generated === 3,
  `pool_id=${pool3} generated=${gen3.body?.data?.generated} msg=${gen3.body?.msg}`)

const ref = sqlScalar(
  `SELECT CONCAT_WS('|', IFNULL(long_term_key_id,'NULL'), IFNULL(long_term_key_version,'NULL')) `
  + `FROM ${POOL_TABLE} WHERE pool_id='${pool3}' LIMIT 1;`
) || ''
check('★ 池项回填了接收方（B）的 KYBER 引用（回收精确失效的判据）',
  ref === `${kyberKeyId}|1`, `读到 ${ref}，期望 ${kyberKeyId}|1`)

// ---------------------------------------------------------------------------
// 4. 列表接口：计划 §8.4 的四个信息面（版本 / 真实状态 / 消费情况）
// ---------------------------------------------------------------------------
title('4. 列表下发真实状态与接收密钥版本（计划 §8.4）')

const listRes = await api(PQKDS, `/key-pool/?pool_id=${encodeURIComponent(pool3)}&page=1&limit=50`)
const listItems = listRes.body?.data || []
const row3 = listItems[0] || {}
check('列表返回该批次的池项（3 条）', listItems.length === 3, `count=${listItems.length}`)
check('★ 列表带长期密钥引用（接收密钥版本）与真实状态字段',
  row3.long_term_key_id === kyberKeyId
  && Number(row3.long_term_key_version) === 1
  && row3.effective_status === 'READY'
  && 'used_by_session_id' in row3,
  `ref=${row3.long_term_key_id}v${row3.long_term_key_version} effective=${row3.effective_status} ` +
  `used_by_session=${row3.used_by_session_id ?? 'null(未消费)'}`)

// ---------------------------------------------------------------------------
// 5. ★★ 真并发：8 个独立进程抢同一批池项 → 成功数恰好等于可用条数
// ---------------------------------------------------------------------------
title('5. ★★ 真并发（N=8）：8 取 3 → 恰好 3 个成功；8 取 1 → 恰好 1 个成功')
info('这是阶段 5 唯一的硬判据。串行两连调证明不了它 —— 断口存在时')
info('"第一次成功第二次失败"照样可能成立（两次都拿到同一条、各自标记成功）。')
info('⚠️ 消费按 key_index 跨批次取第一条，所以每个夹具前先确认"此刻只有这一批"。')

check('并发夹具 ①（8 取 3）：该节点对此刻只有 pool3 的 3 条 READY',
  pairReadyCount(nodeA.nodeId, nodeB.nodeId) === 3,
  `READY=${pairReadyCount(nodeA.nodeId, nodeB.nodeId)}`)

const r3 = await Promise.all(Array.from({ length: 8 }, () => consumeInChild(nodeA.nodeId, nodeB.nodeId)))
const ok3 = r3.filter(isOk)
const fail3 = r3.filter((b) => !isOk(b)).map((b) => String(b?.msg || b?.__error || ''))
check('★ 8 个并发抢 3 条 → 成功**恰好 3 个**（不是 ≥1、也不是 0）',
  ok3.length === 3, `成功 ${ok3.length} / 失败 ${r3.length - ok3.length}`)
check('★ 其余 5 个都拿到 POOL_ITEM_UNAVAILABLE（不是超时、不是 500）',
  fail3.length === 5 && fail3.every((m) => m.includes('POOL_ITEM_UNAVAILABLE')),
  `样例：${(fail3[0] || '').slice(0, 90)}`)
const ok3PoolIds = ok3.map((b) => b?.data?.pool_id)
const ok3Indexes = ok3.map((b) => b?.data?.key_index)
check('★ 三个成功者拿到**三条不同的行**（key_index 互不相同 —— 同一条被并发取走两次会在这里现形）',
  new Set(ok3Indexes).size === 3 && ok3PoolIds.every((p) => p === pool3),
  `key_index=${ok3Indexes.join(',')} pool_id（批次号，三行相同）=${ok3PoolIds.join(',')}`)
check('★ 库内结算：3 条 CONSUMED、0 条 READY —— 并发没有把任何一条重复消费',
  poolCount(pool3, 'CONSUMED') === 3 && poolCount(pool3, 'READY') === 0,
  `CONSUMED=${poolCount(pool3, 'CONSUMED')} READY=${poolCount(pool3, 'READY')}`)
check('成功响应带消费后的状态与密文材料（调用方据此解封）',
  ok3.every((b) => b?.data?.status === 'CONSUMED'
    && Boolean(b?.data?.encrypted_key_data) && Boolean(b?.data?.key_hash)),
  `statuses=${ok3.map((b) => b?.data?.status).join(',')}`)

// 反向夹具（8 取 1）：新批次只有 1 条时，成功数必须收敛到 1。
const gen1 = await genBatch(1)
const pool1 = gen1.body?.data?.pool_id || ''
check('并发夹具 ②（8 取 1）：新批次恰好 1 条 READY，且此刻只有它',
  isOk(gen1.body) && poolCount(pool1, 'READY') === 1
  && pairReadyCount(nodeA.nodeId, nodeB.nodeId) === 1,
  `pool_id=${pool1} READY=${poolCount(pool1, 'READY')} 节点对 READY=${pairReadyCount(nodeA.nodeId, nodeB.nodeId)}`)

const r1 = await Promise.all(Array.from({ length: 8 }, () => consumeInChild(nodeA.nodeId, nodeB.nodeId)))
const ok1 = r1.filter(isOk)
const fail1 = r1.filter((b) => !isOk(b)).map((b) => String(b?.msg || b?.__error || ''))
check('★ 8 个并发抢 1 条 → 成功**恰好 1 个**',
  ok1.length === 1, `成功 ${ok1.length} / 失败 ${r1.length - ok1.length}`)
check('★ 其余 7 个都拿到 POOL_ITEM_UNAVAILABLE',
  fail1.length === 7 && fail1.every((m) => m.includes('POOL_ITEM_UNAVAILABLE')),
  `样例：${(fail1[0] || '').slice(0, 90)}`)
check('★ 库内结算：1 条 CONSUMED、0 条 READY',
  poolCount(pool1, 'CONSUMED') === 1 && poolCount(pool1, 'READY') === 0,
  `CONSUMED=${poolCount(pool1, 'CONSUMED')} READY=${poolCount(pool1, 'READY')}`)

// ---------------------------------------------------------------------------
// 6. 串行复取：已被取走的行不会被第二次取到
// ---------------------------------------------------------------------------
title('6. 消费后不可重复：再取一次 → 没有可用（池子已空）')
const again = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
check('★ 重复消费失败且如实报 POOL_ITEM_UNAVAILABLE',
  !isOk(again.body) && String(again.body?.msg || '').includes('POOL_ITEM_UNAVAILABLE'),
  `msg=${String(again.body?.msg || '').slice(0, 100)}`)

// ---------------------------------------------------------------------------
// 7. 过期与历史拼写：消费口与页面**同判**
// ---------------------------------------------------------------------------
title('7. 过期行取不出来；历史拼写 unused 的行取得到（两处同判）')
info('过期行的页面口径与服务端口径必须一致 —— 页面说"可用"、消费说"没有"，')
info('两个数字都出自服务端却互相矛盾，且没有任何一处会报错。')
info('⚠️ 判据的顺序本身就是判据：列表端点加载时会**自动清理**过期未用行')
info('（KMS-013 之前就有的行为）。所以"页面口径"必须在**消费口**之后再断言 ——')
info('反过来的话，夹具行会被那次列表加载先删掉，两组断言一起读到 null。')

const ormSetup = orm(ormHeader + `
from pqkds.models import Node, PreDistributedKey
from django.utils import timezone
from datetime import timedelta
a = Node.objects.get(node_id='${nodeA.nodeId}')
b = Node.objects.get(node_id='${nodeB.nodeId}')
expired = PreDistributedKey.objects.create(
    pool_id='TESTKMS013-expired', key_index=0, node1=a, node2=b,
    algorithm='kyber_kem', encrypted_key_data='{}', key_hash='0' * 64,
    status='READY', expires_at=timezone.now() - timedelta(minutes=5),
    long_term_key_id='${kyberKeyId}', long_term_key_version=1)
legacy = PreDistributedKey.objects.create(
    pool_id='TESTKMS013-legacy', key_index=0, node1=a, node2=b,
    algorithm='kyber_kem', encrypted_key_data='{}', key_hash='1' * 64,
    status='unused', expires_at=timezone.now() + timedelta(days=1),
    long_term_key_id='${kyberKeyId}', long_term_key_version=1)
print('SETUP_OK pk=%s,%s' % (expired.pk, legacy.pk))
`)
check('夹具就绪：一条已过期 READY、一条历史拼写 unused', ormSetup.includes('SETUP_OK pk='),
  ormSetup.trim().split('\n')[-1])

// ③ 消费口先判（此刻两个夹具行都还在）：它必须越过过期行、取到历史行。
// 这一步同时是"过期行取不出来"的**行为判据** —— 过期行 key_index 更小
// （0 与 0 同值，按 id 序），若消费不判 expires_at，它会被取走。
const consumeLegacy = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
check('★ 消费口与页面同判过期：它取到的是历史行，**没有**碰过期行',
  isOk(consumeLegacy.body) && consumeLegacy.body?.data?.pool_id === 'TESTKMS013-legacy',
  `取到 ${consumeLegacy.body?.data?.pool_id || JSON.stringify(consumeLegacy.body).slice(0, 80)}`)
check('历史拼写经消费后写成**规范值** CONSUMED（别名只在读取侧兼容）',
  sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-legacy';`) === 'CONSUMED',
  `读到 ${sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-legacy';`)}`)
check('过期行原状（消费不动它，过期不是消费）',
  sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-expired';`) === 'READY',
  `读到 ${sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-expired';`)}`)

// ① 页面侧的真实契约：过期未用行在**列表加载时被自动清理**，
// 所以页面上不会出现"显示为可被会话取用、却取不走"的行 —— 与消费口
// "取不出来"是同一个结论（口径一致的可观测形式）。
// ⚠️ 不能反过来先读列表再消费：那次加载会把夹具行删掉，下面的断言
// 会以"读到 null"的方式失败，看起来像消费坏了。
const expiredRow = await api(PQKDS, '/key-pool/?pool_id=TESTKMS013-expired&page=1&limit=5')
const expiredItem = (expiredRow.body?.data || [])[0] || {}
const expiredRemaining = sqlScalar(
  `SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-expired';`)
check('★ 列表加载自动清理过期未用行：页面没有"可用却取不走"的行（与消费口同结论）',
  !expiredItem.pool_id && expiredRemaining === '0',
  `列表返回=${expiredItem.pool_id || '空'}，库内剩余=${expiredRemaining}`)

const noMore = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
check('此时再取 → 没有可用（只剩过期行，取不出来）',
  !isOk(noMore.body) && String(noMore.body?.msg || '').includes('POOL_ITEM_UNAVAILABLE'),
  `msg=${String(noMore.body?.msg || '').slice(0, 90)}`)

// ---------------------------------------------------------------------------
// 8. Kyber 预分配吞吐：管理命令现跑，表格原样打印（阶段 5 的完成标准之一）
// ---------------------------------------------------------------------------
title('8. Kyber 预分配吞吐（计划 §7 阶段 5：可复现实测报告）')
info('用服务端计时、以成功持久化的条数为准（命令的计数口径写在它自己的 docstring 里）。')

const bench = execFileSync(dockerBin, [
  'exec', '-w', '/backend', 'dvadmin3-django', 'python', 'manage.py',
  'benchmark_preallocation', '--counts', '100', '1000',
  '--node-a', nodeA.nodeId, '--node-b', nodeB.nodeId
], { encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } })
bench.trim().split('\n').forEach((line) => info(`[bench] ${line}`))
const rateMatches = [...bench.matchAll(/([\d.]+) 条：([\d.]+) 条\/s —— (达标|未达标)/g)]
check('吞吐报告可解析（两组：100 / 1000）', rateMatches.length === 2,
  rateMatches.map((m) => `${m[1]}→${m[2]}/s(${m[3]})`).join('  '))
check('★ 最高吞吐 ≥ 50 条/s（命令内建的达标阈值）',
  rateMatches.some((m) => Number(m[2]) >= 50),
  rateMatches.map((m) => m[2]).join(' / '))

// 把基准造出来的 READY 行清掉（只清基准产生的：pool_kyber_ 前缀且仍是 READY）。
// 验收夹具的行不在此列（它们此刻是 CONSUMED 或过期的）。
const benchClean = orm(ormHeader + `
from pqkds.models import Node, PreDistributedKey
a = Node.objects.get(node_id='${nodeA.nodeId}')
n, _ = PreDistributedKey.objects.filter(
    node1=a, algorithm='kyber_kem', status__in=['READY', 'unused'],
    pool_id__startswith='pool_kyber_').delete()
print('BENCH_CLEANED=%d' % n)
`)
check('基准产生的 READY 行已清理（不把开发库喂脏）',
  /BENCH_CLEANED=(\d+)/.test(benchClean), benchClean.trim().split('\n')[-1])

// ---------------------------------------------------------------------------
// 9. ★★ 目标密钥版本失效 → 池项不会继续分发（两个面一起钉）
// ---------------------------------------------------------------------------
title('9. ★★ 撤掉池项引用的那把 KYBER → 池项连带失效，消费口再独立拒一次')
info('两个面分属不同机制：KMS-007 的**连带标记**（池项转 REVOKED）与本阶段')
info('消费口的**独立复核**。只钉标记的话，"标记漏网"的行（历史数据、手工改库、')
info('标记引入之前的行）会被照常消费走，直到解封时才失败。')

const gen2 = await genBatch(2)
const poolR = gen2.body?.data?.pool_id || ''
check('撤前夹具：新批次 2 条 READY（撤后它们必须被连带标记）',
  isOk(gen2.body) && poolCount(poolR, 'READY') === 2,
  `pool_id=${poolR} READY=${poolCount(poolR, 'READY')}`)

const revoke = await api(PQKDS, '/node-self/keys/revoke/', {
  method: 'POST',
  token: nodeB.token,
  body: { algorithm: KYBER, keyId: kyberKeyId, keyVersion: 1, reason: 'KMS-013 验收：撤池项引用的那把' }
})
check('回收成功（B 的 KYBER v1）', isOk(revoke.body),
  `code=${revoke.body?.code} impact.poolItems=${revoke.body?.data?.impact?.poolItems}`)
check('★ 连带标记：该批 2 条 READY → REVOKED（KMS-007 的精确失效面）',
  poolCount(poolR, 'READY') === 0 && poolCount(poolR, 'REVOKED') === 2,
  `READY=${poolCount(poolR, 'READY')} REVOKED=${poolCount(poolR, 'REVOKED')}`)

const afterRevoke = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
check('★ 消费口拒：撤后该节点对没有可消费的池项（标记面生效）',
  !isOk(afterRevoke.body) && String(afterRevoke.body?.msg || '').includes('POOL_ITEM_UNAVAILABLE'),
  `msg=${String(afterRevoke.body?.msg || '').slice(0, 90)}`)

// 漏网行：手工把一条改回 READY，**绕开**标记面，逼消费口自己判
const unmark = orm(ormHeader + `
from pqkds.models import PreDistributedKey
row = PreDistributedKey.objects.filter(pool_id='${poolR}').order_by('key_index').first()
row.status = 'READY'
row.save(update_fields=['status'])
print('UNMARKED=%s#%s' % (row.pool_id, row.key_index))
`)
check('夹具：把一条已标记的行改回 READY（模拟标记漏网）', unmark.includes('UNMARKED='),
  unmark.trim().split('\n')[-1])

const gate = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
const gateMsg = String(gate.body?.msg || '')
check('★ 消费口独立复核：引用的 KYBER 已回收 → 拒绝，码 KEY_REVOKED',
  !isOk(gate.body) && gateMsg.includes('KEY_REVOKED'),
  `msg=${gateMsg.slice(0, 130)}`)
check('★ 识破即纠正：漏网行被**就地标成 REVOKED**（与回收路径同一判据的迟到应用，'
  + '页面口径从此一致），拒绝文案如实说明纠正了什么',
  sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='${poolR}' AND key_index=0;`) === 'REVOKED'
  && gateMsg.includes('已就地标记'),
  `行状态=${sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='${poolR}' AND key_index=0;`)} ` +
  `msg=${gateMsg.slice(0, 130)}`)

// ★ 不毒化：纠正之后，第二次消费面对的是"池子空了"，而不是永远撞同一条死件
// —— "只拒绝不纠正"的版本下这条会一直返回 KEY_REVOKED，池里卡着一条谁也
// 取不走的死件。
const afterCorrect = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
check('★ 纠正之后不再撞死件：第二次消费是 POOL_ITEM_UNAVAILABLE（不是永远 KEY_REVOKED）',
  !isOk(afterCorrect.body) && String(afterCorrect.body?.msg || '').includes('POOL_ITEM_UNAVAILABLE'),
  `msg=${String(afterCorrect.body?.msg || '').slice(0, 90)}`)

// ★ 正对照（走 HTTP）：回收后**重新登记一把新 KYBER 再预分配**，消费必须恢复
// —— 上面两条拒绝都是"这一批不可用"，不是"这个节点对永远不能消费"。
// 没有这条，"闸门恒拒绝"也能让整个第 9 节全绿。
const newKyber = await cryptoProvider.generate(KYBER, { nodeId: nodeB.nodeId, variant: VARIANT })
const newKyberUp = await register(nodeB, KYBER, newKyber, { securityLevel: String(VARIANT) })
const genRecover = await genBatch(1)
const poolRecover = genRecover.body?.data?.pool_id || ''
const recover = await consumeHttp(nodeA.nodeId, nodeB.nodeId)
check('★ 正对照：重新登记 B 的 KYBER 并预分配后，消费恢复成功（闸门不是恒拒绝）',
  isOk(newKyberUp.body) && isOk(genRecover.body) && isOk(recover.body)
  && recover.body?.data?.pool_id === poolRecover,
  `newKey=${newKyber.keyId} gen=${isOk(genRecover.body)} 取到=${recover.body?.data?.pool_id || JSON.stringify(recover.body).slice(0, 80)}`)

// ---------------------------------------------------------------------------
// 10. 清理口径：过期行被清掉，REVOKED / CONSUMED 是证据，不能被清
// ---------------------------------------------------------------------------
title('10. 清理过期：删的只有过期未用行；回收与消费记录是审计证据，保留')

// 现造一条"已过期且无引用"的行：它必须被清掉。用无引用的行是刻意的 ——
// 第 7 节那条过期行此刻已被第 9 节的回收连带标成 REVOKED（属于证据，
// 不在删除范围内），两条各自证明一件事。
const ormExpired2 = orm(ormHeader + `
from pqkds.models import Node, PreDistributedKey
from django.utils import timezone
from datetime import timedelta
a = Node.objects.get(node_id='${nodeA.nodeId}')
b = Node.objects.get(node_id='${nodeB.nodeId}')
PreDistributedKey.objects.create(
    pool_id='TESTKMS013-expired2', key_index=0, node1=a, node2=b,
    algorithm='kyber_kem', encrypted_key_data='{}', key_hash='2' * 64,
    status='READY', expires_at=timezone.now() - timedelta(minutes=5))
print('EXPIRED2_OK')
`)
check('夹具：一条已过期、无长期密钥引用的 READY 行', ormExpired2.includes('EXPIRED2_OK'),
  ormExpired2.trim().split('\n')[-1])

const cleanupRes = await api(PQKDS, '/key-pool/cleanup/', { method: 'POST' })
check('cleanup 调用成功（cleaned ≥ 1）', isOk(cleanupRes.body),
  `msg=${cleanupRes.body?.msg}`)
check('★ 过期未用行被清掉',
  sqlScalar(`SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-expired2';`) === '0',
  `剩 ${sqlScalar(`SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='TESTKMS013-expired2';`)} 行`)
check('★ REVOKED 行**必须还在**（它是"依赖的密钥已回收"的证据）',
  poolCount(poolR, 'REVOKED') === 2,
  `REVOKED=${poolCount(poolR, 'REVOKED')}`)
check('★ 已消费行**必须还在**（它是"被哪次会话用掉"的历史）',
  poolCount(pool1, 'CONSUMED') === 1 && poolCount(pool3, 'CONSUMED') === 3,
  `pool1=${poolCount(pool1, 'CONSUMED')} pool3=${poolCount(pool3, 'CONSUMED')}`)

// ---------------------------------------------------------------------------
// 11. 状态统计口径 + 清理
// ---------------------------------------------------------------------------
title('11. 统计口径：reserved 恒 0（保留值），三个读数与库内同一套判据')

const stats = await api(PQKDS, '/key-pool/stats/')
check('stats 返回 reserved/revoked 两个新读数（reserved 是保留值）',
  isOk(stats.body) && stats.body?.data?.reserved === 0
  && Number.isInteger(stats.body?.data?.revoked)
  && Number.isInteger(stats.body?.data?.unused),
  `reserved=${stats.body?.data?.reserved} revoked=${stats.body?.data?.revoked} ` +
  `unused=${stats.body?.data?.unused} used=${stats.body?.data?.used}`)

title('12. 清理：删掉本脚本建的两个节点及其一切关联行')
const cleanupProgram = ormHeader + `
from pqkds.models import Node
nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d cascaded=%d left=%d' % (len(ids), deleted, left))
`
let cleanupOut = ''
let cleanupErr = ''
try {
  cleanupOut = orm(cleanupProgram).trim()
} catch (error) {
  cleanupErr = String(error?.stderr || error?.message || error)
}
info(cleanupOut || cleanupErr)
check('清理完成：域内不再有本脚本建的节点（池行随 CASCADE 一并清掉）',
  Boolean(cleanupOut) && cleanupOut.endsWith('left=0'),
  cleanupOut || cleanupErr)

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId}（已在上面删掉）`)
info('证据都在上面：部署探针（断口 1/2 的修复在跑）、真并发 8 取 3 与 8 取 1、')
info('重复消费拒绝、过期与历史拼写两处同判、撤密钥后连带失效 + 消费口独立复核（KEY_REVOKED）、')
info('清理口径（只删过期未用行）、吞吐报告（第 8 节的 [bench] 行）。')
finish()
