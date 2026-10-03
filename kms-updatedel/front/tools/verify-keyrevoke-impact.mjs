/**
 * KMS-007 验收：**回收一把长期密钥之后，系统里还有谁把它当可用**。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 计划 §12 阶段 2 的四条完成标准（文档 229-234 行）里，本次任务负责后两条：
 *   ③ 回收后的接口返回明确错误码，如 KEY_REVOKED；
 *   ④ 更新、回收事件能够正确进入审计和链上记录（"更新"那一半由 KMS-006 验）。
 * 两条都不能用"调用没报错"证明：
 *
 *   * ③ 的失败形态**恰恰是 200**。三个响应约定并存是既有事实：
 *     `/node-self/*` 恒 HTTP 200、错误码在 `body.data.error_code`；
 *     `/key-pool/*` 恒 HTTP 200、错误码**没有字段**、只出现在 `msg` 文本里；
 *     `distribute-to-user` 用真 HTTP 状态码（KEY_REVOKED → 409）。
 *     而"回收后还能用"的表现不是报错，是**照常成功** —— 池项还是 READY、
 *     信封照发、会话照建。所以每条断言都必须指名"哪个字段里应当出现
 *     KEY_REVOKED"，不能写成 `!isOk(...)`（那对"参数写错了"也成立）。
 *   * ④ 的链上一半按设计**不落库表**：`record_chain_event` 打的是生命周期服务的
 *     internal 接口，失败只返回空串、且在事务**之外**被调用。所以"已回收"与
 *     "已上链"是两条独立证据，必须分开读 —— 合成一句"成功"会把审计缺口盖掉。
 *     库内那一半的证据是密钥自己那一行（status / revoked_at / revoked_reason），
 *     **不是** `OperationLog`：`/node-self/*` 全是函数视图，写日志的中间件
 *     只对带 `queryset` 的类视图建行，拿它当审计证据会恒为"没落库"。
 *
 * 为什么先跑部署探针
 * ----------------
 * 本仓库的后端代码是**打进镜像**的（没有 bind mount），`docker cp` 进去的文件
 * 只活在容器可写层、进程不重启就 import 不到 —— 磁盘上的文件却是新的
 * （md5 都对得上）。这种状态下的表现极具欺骗性：回收路由不存在时返回 404/405，
 * 后面每一条断言都会以"没读到字段"的方式失败，看起来像逻辑错。
 * 所以第 1 节先探"跑着的服务端到底有没有这段代码"，探不过就**直接退出**，
 * 不让一次部署问题伪装成十几个逻辑缺陷（KMS-006 踩过这个坑）。
 *
 * 影响面里最要紧的一条
 * ------------------
 * 第 5 节把 `revoke_pool_items_for_key` 改前的缺陷钉进断言：改前它**只按 node
 * 匹配**，撤一把密钥会把该节点**全部** READY/RESERVED 池项一起清掉，而日志逐字
 * 印着 key_id/version，读日志的人会以为它是精确失效的。
 *
 * 精确面是**两列**（`long_term_key_id` + `long_term_key_version`，迁移 0017），
 * 所以夹具用三个池子把两个维度分开测：
 *
 *     池子        引用                     第 5 节撤 K2/v2 之后
 *     poolK1      K1/v1（另一个 keyId）    必须 READY 满员（不许误伤）
 *     poolK2v1    K2/v1（同 keyId 老版本） 必须 READY 满员（不许误伤）
 *     poolK2v2    K2/v2（回收目标）        必须全部 REVOKED
 *
 * 引用靠"生成池时回填消费方那把长期密钥"（D3）：B 的 KYBER 先换 keyId、再升一版，
 * 每换一次生成一个池子。改前的实现会让两条"必须还活着"全灭，且 `impact.poolItems`
 * 报 7 而不是 3 —— 三个断言同时抓住它。
 *
 * ⚠️ 这里原本还有一个"另一种算法（FALCON）的池项必须还活着"的对照，本次换掉了：
 *    `generate_falcon_pool` 对当前登记链路是**死的** —— 它把 `node2.falcon_public_key`
 *    交给 `encrypt_aes_key_with_falcon`，后者要的是 CL-Falcon **格材料** JSON，而该列
 *    自登记链路改存标准 NIST Falcon 公钥（hex）之后必然解析失败：循环里逐条
 *    `continue`，接口仍回 `success:true, generated:0`。这是**既有断口**（本次改动面
 *    不含 `falcon_aes_session_encryption.py` 与 `node_service.py`），修它等于替整个
 *    CL-Falcon 池设计的去留做决定（KMS-014 量级）。留在原地的后果是那个对照**恒为
 *    空池**、两条断言空洞地通过 —— 换成上面这套真能证伪的夹具。
 *
 * ⚠️ 会**建真节点、写真数据**（`falcon_kds` 与浏览器存储都会变），
 *    只在本地验证环境跑。结尾第 9 节自建自清 —— KMS-005/006 的旧脚本不清理，
 *    开发库的节点数一直在涨（写这份时库里已有 47 个）。
 *
 * 独立复核（doc/kms-007-verify.md）点名的四处空心断言，本版逐一补齐
 * ----------------------------------------------------------------
 * 复核判词是「实现全坏也会绿」，四处都属这一类 —— 补法是让断言读**独立证据**，
 * 而不是把自己刚收到的响应再念一遍：
 *
 *   ① 链上只断言 `Boolean(chainHash)`。那个哈希只证明"回执里解出了至少一个
 *      `KeyLifecycleEvent`" —— `eventType` 写成 KEY_UPDATED、keyId/版本/节点
 *      写错，哈希照回。补法见 §5.2：按交易哈希回读链上事件，逐字段比对；
 *      重试后再**数一次该 keyId 的 KEY_REVOKED 事件条数**，证明不重复上链。
 *      ⚠️ 这是唯一一处**不是**从服务端响应取证的地方 —— 响应可以自证清白，
 *      链不行（回执由 4 个共识节点签出）。
 *   ② ①/④/⑤ 三条闸门在回收前**从未成功调用过**。后果：一条"这三条闸门永远
 *      拒绝"的回归会让三条断言全绿。补法见 §3.5（① 与 ④ 各成功一次）与
 *      §3.6（⑤ 的放行态：真签一次名并核对信封里带上了签名）。
 *   ③ 会话影响面只断言 `sessions >= 1`。夹具只有一条会话，"过度失效"（把
 *      无关会话也撤了）与正确实现都满足它。补法见 §4.6：加一条**无关节点对**
 *      的活跃会话，断言它保持 active；目标节点会话数收紧为 `=== 1`。
 *   ④ ③"被拒之后没有多出任何池项"写成了
 *      `poolCounts(pool_id || 'no-such-pool').total === 0 || pool_id === undefined`
 *      —— 被拒响应本来就不带 pool_id，两个析取支同时平凡为真。补法见 §5.3：
 *      记录回收前后该节点对（A,B）的**全局**池行数，断言计数之差为 0。
 */
import { execFileSync } from 'node:child_process'

import {
  ORIGIN,
  PQKDS,
  UPDATEDEL_API,
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
const FALCON = 'FALCON'
const VARIANT = 768

/**
 * 用户腿信封的加密目标：一个**真实的** sm2p256v1 曲线点。
 *
 * ⚠️ 公钥，不是秘密。但它必须是曲线方程的真解 —— KGC 在 `keymanage` 里会验
 *    曲线方程，随手编一串 hex 会被拒，而拒的理由看起来像"参数格式不对"。
 */
const UA = '04573e32965ced2ca54c9f9a26be3c5115f83f61bc0d7ed72b90ffb9cce6b741235c0e249f323ad7703340983665e5147c6893490242af26fa642372a899a74c30'

/** 本脚本建的节点都打这个域标记，清理时按它捞 —— 见第 9 节的说明。 */
const DOMAIN = 'kms007'

// ---------------------------------------------------------------------------
// 查链
// ---------------------------------------------------------------------------
/**
 * FISCO 节点的 JSON-RPC 端口（compose 里**只绑回环**，见 `kms-ops/docker-compose.yml`
 * 的 `127.0.0.1:8545:8545`）。脚本跑在宿主上，所以直连 —— 不经容器。
 *
 * ⚠️ 为什么不走 `kms_fisco_console`：那个容器里的 `java` 进程每次调用要约 10 秒
 *    （JVM 启动 + SDK 初始化），跑一轮 40+ 次读取代价太大；而 JSON-RPC 的
 *    返回结构与控制台打印的是同一份数据（控制台自己就是它的包装）。
 */
const FISCO_RPC = 'http://127.0.0.1:8545'
/** group id。链上只有 1 组，写死比从配置读更不容易读错。 */
const FISCO_GROUP = 1
/**
 * `KeyEvidence` 合约地址 —— 与 `kms-ops/.env` 的 `FISCO_CONTRACT_ADDRESS` 同一个值。
 *
 * ⚠️ 不在这里动态解析 `.env`：链上回读要断言的正是"事件确实来自那个被部署的
 *    合约"，从被测系统读它的配置等于让它自己证明自己 —— 地址写错时两边一起错，
 *    断言照样绿。写成常量后，地址漂移会让"回执里根本没有事件"直接暴露。
 */
const CONTRACT = '0xb7a03cd7da5553239faa9357a795f0c6015fcdda'
/**
 * `KeyLifecycleEvent(string,uint256,uint32,string,string,uint256)` 的**签名哈希**
 * —— 即 `topics[0]`。它由事件签名自身决定，与合约地址、参数值都无关。
 */
const EVENT_TOPIC = '0x22de73619d629ec7133d447cdf4518a474ff2e04167d013fe27d8ae0022716b0'

/**
 * 调一次 JSON-RPC。⚠️ 请求体里带 `groupId`（FISCO 专有），缺了会报
 * `INVALID_PARAMS` —— 那是**参数错**不是"方法不支持"，两种都返回 error 对象，
 * 靠 message 区分，所以这里把它原样抛出来而不是吞掉。
 */
async function rpc(method, params) {
  const res = await fetch(FISCO_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 })
  })
  const json = await res.json()
  if (json.error) throw new Error(`${method} 失败：${json.error.message || JSON.stringify(json.error)}`)
  return json.result
}

/** ABI 解码：把 32 字节定长字读成 BigInt（不用 Number —— keyId 是无符号 256 位）。 */
const word = (hex, i) => BigInt('0x' + hex.slice(i * 64, (i + 1) * 64))
/** ABI 解码：读动态 `string`（第 i 个字是相对 data 起点的字节偏移）。 */
function abiString(hex, i) {
  const off = Number(word(hex, i)) * 2
  const len = Number(BigInt('0x' + hex.slice(off, off + 64))) * 2
  return Buffer.from(hex.slice(off + 64, off + 64 + len), 'hex').toString('utf8')
}

/**
 * 从一条 log 解出 `KeyLifecycleEvent` 的事件本体。
 *
 * 事件签名（`KeyEvidence.sol`）：
 *   `KeyLifecycleEvent(string eventType, uint256 indexed keyId, uint32 version,
 *                      string nodeId, string publicMaterialHash, uint256 timestamp)`
 *
 * ⚠️ 动态字段的 data 布局与函数参数**不同**：索引参数（`keyId`）不进 data，
 *    只进 topics；所以 data 的第一个字是 `eventType` 的偏移，不是 keyId。
 *    把 topics 与 data 混起来读会解出看似合理但完全错位的值。
 */
function decodeLifecycleEvent(log) {
  const hex = log.data.slice(2)
  return {
    keyId: BigInt(log.topics[1]),
    eventType: abiString(hex, 0),
    version: Number(word(hex, 1)),
    nodeId: abiString(hex, 2),
    materialHash: abiString(hex, 3),
    timestamp: word(hex, 4)
  }
}

/**
 * 遍历全链，收集所有 `KeyLifecycleEvent`。
 *
 * ⚠️ 为什么是**遍历**而不是 `getPastLogs`：本链的节点不支持那个方法
 *    （实测回 `METHOD_NOT_FOUND`），而 `getBlockNumber` / `getBlockByNumber` /
 *    `getTransactionReceipt` 都在。开发链的块数很小（写这份时 175），
 *    全量扫的代价可以忽略；换到长链上要改成按块号区间分段查。
 *
 * ⚠️ `getBlockByNumber` 的第二个参数在 FISCO 上是 **groupId**（不是
 *    "return full tx"），第三个数才是那个布尔；参数顺序写错会拿到
 *    "block 不存在"或参数错，两者都与"这个块里没有事件"长得不一样 —— 会报错。
 */
async function scanLifecycleEvents() {
  const head = Number(await rpc('getBlockNumber', [FISCO_GROUP]))
  const events = []
  for (let n = 0; n <= head; n += 1) {
    const block = await rpc('getBlockByNumber', [FISCO_GROUP, '0x' + n.toString(16), true])
    for (const tx of (block.transactions || [])) {
      const receipt = await rpc('getTransactionReceipt', [FISCO_GROUP, tx.hash])
      if (!receipt) continue
      for (const log of (receipt.logs || [])) {
        if (log.topics?.[0] !== EVENT_TOPIC) continue
        events.push({ txHash: tx.hash, block: n, contract: log.address, ...decodeLifecycleEvent(log) })
      }
    }
  }
  return events
}

/** 某把 keyId 的 `KEY_REVOKED` 事件（按交易哈希去重 —— 同一条事件可能被读两次）。 */
function revokedEventsFor(events, keyId, nodeId) {
  const seen = new Set()
  return events.filter((e) => {
    if (e.eventType !== 'KEY_REVOKED' || e.keyId !== BigInt(keyId) || e.nodeId !== nodeId) return false
    if (seen.has(e.txHash)) return false
    seen.add(e.txHash)
    return true
  })
}

// ---------------------------------------------------------------------------
// 查库
// ---------------------------------------------------------------------------
const NODE_TABLE = 'falcon_kds.dvadmin_pqkds_nodes'
const LTK_TABLE = 'falcon_kds.dvadmin_pqkds_node_long_term_keys'
const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const SESSION_TABLE = 'falcon_kds.dvadmin_pqkds_session_keys'
const INVALIDATION_TABLE = 'falcon_kds.dvadmin_pqkds_session_key_invalidations'
/** 用户腿信封 —— ⑤ 正对照要在这里核对签名，而不是节点腿的池行（见该处注释）。 */
const ENVELOPE_TABLE = 'falcon_kds.dvadmin_pqkds_user_key_envelopes'

/**
 * `NodeLongTermKey.node` 的外键列名是 `node_id`，存的是 `Node` 的**整数主键**
 * —— 不是业务编号 `Node.node_id`（模型里是 `ForeignKey(Node)`，无 `to_field`）。
 *
 * ⚠️ 按业务编号查长期密钥**必须**走这个子查询：直接写 `WHERE node_id='KRA-XX'`
 *    会**恒不命中却不报错**（整数列与字符串比较），读回空值，随后的断言就走错
 *    分支 —— 而"空"看起来只是"这个节点还没登记过"。
 */
const ownerId = (nodeId) =>
  `(SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeId}')`

/** 一行长期密钥的三段事实：版本 | 状态 | 生产槽位。取不到返回 null。 */
function ltKeyFact(nodeId, algorithm, keyId, version) {
  // `CONCAT_WS` 会跳过 NULL，用 IFNULL 占位，否则"槽位为空"的结果会少一段。
  return sqlScalar(
    `SELECT CONCAT_WS('|', key_version, status, IFNULL(active_slot, 'NULL')) FROM ${LTK_TABLE} `
    + `WHERE node_id=${ownerId(nodeId)} AND algorithm='${algorithm}' `
    + `AND key_id='${keyId}' AND key_version=${Number(version)};`
  )
}

/**
 * 审计那两半的**库内**一半：回收原因 | revoked_at 是否已写。
 *
 * ⚠️ `sqlScalar` 在没有行时返回 `null`（不是空串）。调用方一律 `|| ''` 再
 *    `.includes(...)`，**不要**包 `String()` —— 那会把 null 变成字符串 'null'，
 *    于是"这行不存在"和"这行的原因里有 null 四个字母"分不出来。
 */
function ltRevoked(nodeId, algorithm, keyId, version) {
  return sqlScalar(
    `SELECT CONCAT_WS('|', IFNULL(revoked_reason, 'NULL'), IF(revoked_at IS NULL, 'NULL', 'SET')) `
    + `FROM ${LTK_TABLE} WHERE node_id=${ownerId(nodeId)} AND algorithm='${algorithm}' `
    + `AND key_id='${keyId}' AND key_version=${Number(version)};`
  ) || ''
}

/**
 * `Node.<算法>_public_key` 物化列是否**逐字节**等于给定值。
 *
 * ⚠️ 两侧都加 `BINARY`：MySQL 默认排序规则不区分大小写，不加的话
 *    `'AB' = 'ab'` 为真 —— 而这条断言的全部意义就是"逐字节相同"。
 */
function nodeColumnIs(nodeId, column, expected) {
  return sqlScalar(
    `SELECT (BINARY IFNULL(${column}, '') = BINARY '${expected}') `
    + `FROM ${NODE_TABLE} WHERE node_id='${nodeId}';`
  ) === '1'
}

/** 一个池子里的状态分布：READY / REVOKED / 总数。没有行时全 0。 */
function poolCounts(poolId) {
  const raw = sqlScalar(
    `SELECT CONCAT_WS('|', IFNULL(SUM(status='READY'), 0), IFNULL(SUM(status='REVOKED'), 0), COUNT(*)) `
    + `FROM ${POOL_TABLE} WHERE pool_id='${poolId}';`
  ) || '0|0|0'
  const [ready, revoked, total] = raw.split('|').map((n) => Number(n))
  return { ready, revoked, total }
}

/** 池项自己记着的长期密钥引用（`NULL` 时是字符串 'NULL'，用来分辨"没引用"）。 */
function poolKeyRef(poolId, algorithm) {
  return sqlScalar(
    `SELECT CONCAT_WS('|', IFNULL(long_term_key_id, 'NULL'), IFNULL(long_term_key_version, 'NULL')) `
    + `FROM ${POOL_TABLE} WHERE pool_id='${poolId}' AND algorithm='${algorithm}' LIMIT 1;`
  ) || ''
}

const sessionStatus = (sessionId) =>
  sqlScalar(`SELECT status FROM ${SESSION_TABLE} WHERE session_id='${sessionId}';`) || ''

const sessionIdOf = (sessionId) =>
  `(SELECT id FROM ${SESSION_TABLE} WHERE session_id='${sessionId}')`

function invalidationFact(sessionId) {
  return sqlScalar(
    `SELECT CONCAT_WS('|', reason, invalidated_node_id) FROM ${INVALIDATION_TABLE} `
    + `WHERE session_id=${sessionIdOf(sessionId)} ORDER BY id DESC LIMIT 1;`
  ) || ''
}

const invalidationCount = (sessionId) =>
  Number(sqlScalar(`SELECT COUNT(*) FROM ${INVALIDATION_TABLE} WHERE session_id=${sessionIdOf(sessionId)};`) || 0)

/**
 * 某个**节点对**在全局池表里的行数（两个方向都算）。
 *
 * ⚠️ 这是复核点名要换上的那条断言（原版是"被拒响应没带回 pool_id，所以池子为空"——
 *    两个析取支同时平凡为真）。按节点对计数是**独立证据**：不管接口回没回
 *    pool_id、也不管池子是哪个 pool_id，只要这一对被拒的预分配偷偷落了行，
 *    计数就会涨。
 *
 * ⚠️ 用 `IN (a, b)` 的两个方向，而不是 `node1=a AND node2=b`：池子的两个节点
 *    在表里谁排前排后取决于调用方怎么传，写死一个方向会**恒为 0** —— 那正是
 *    "断言永远为真"的另一种写法。
 */
const pairPoolRows = (nodeId1, nodeId2) => Number(sqlScalar(
  `SELECT COUNT(*) FROM ${POOL_TABLE} `
  + `WHERE (node1_id=${ownerId(nodeId1)} AND node2_id=${ownerId(nodeId2)}) `
  + `   OR (node1_id=${ownerId(nodeId2)} AND node2_id=${ownerId(nodeId1)});`
) || 0)

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------
/**
 * 登记 / 更新一个公钥。`extra.rotate` 是**更新页**的语义（同一个 keyId 升版本），
 * 必须显式转发（照抄 `verify-keyupdate-rotate.mjs` 的同名助手）。
 *
 * ⚠️ 漏掉这个字段不会报错：服务端把 `rotate` 默认按 False 读，于是"更新"静默退化
 *    成"带显式版本的登记"—— 而两者在**成功路径**下落库完全一致（旧版降级 RETIRED、
 *    新版 ACTIVE、物化列指向新版）。第 4 节那句"msg 里含『已更新』"就是为此留的。
 */
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
      keyVersion: material.version,
      ...(extra.rotate ? { rotate: true } : {})
    }
  })

const errCodeOf = (body) => body?.data?.error_code || '(无 error_code)'

/** 回收本节点的一把密钥（三个字段原样转发，见 node-self.js 的同名函数）。 */
const revoke = (session, algorithm, keyId, keyVersion, reason) =>
  api(PQKDS, '/node-self/keys/revoke/', {
    method: 'POST',
    token: session.token,
    body: { algorithm, keyId, keyVersion, reason }
  })

/**
 * 在容器里现生成一把**真** Falcon-512 密钥对，返回 base64 的两半。
 *
 * 为什么要真密钥而不是随便一串 hex：⑤ 那道闸门有两条分支 —— 登记表说不可用
 * 时拒绝（§6 测的），以及可用时**照常签名**。要证明"放行分支真的在跑"，
 * 就得让签名那一步真的成功：`sign_envelope` 会 `base64.b64decode` 私钥列，
 * 再比对长度与 Falcon-512 期望的 1281 字节，最后交给 DLL 真签一次。
 * 喂垃圾进去会在第一步就返回 None，信封拿不到签名 —— 那与"放行分支根本没接上"
 * 无法区分，正是复核说的"永远拒绝"型回归看不见的地方。
 *
 * ⚠️ 走 Django ORM 的 DLL 而不是在 Node 侧生成：Falcon 的实现是
 *    `crypto_utils.FalconCrypto`，它加载的是容器里的 `falcon-kds-有陷门` 那个
 *    动态库；浏览器 provider 用的是 `@noble/post-quantum`，**两套实现的
 *    密钥编码不保证互通**（文件头那句"round-3 不是 ML-KEM"是同一类坑）。
 */
function generateFalconKeypair() {
  const program = `
import base64, sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django; django.setup()
from pqkds.crypto_utils import FalconCrypto
pk, sk = FalconCrypto(512).generate_keypair()
print('PK=' + base64.b64encode(pk).decode())
print('SK=' + base64.b64encode(sk).decode())
`
  const out = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
    input: program,
    encoding: 'utf8',
    env: { ...process.env, MSYS_NO_PATHCONV: '1' }
  })
  const pk = (out.match(/^PK=(\S+)$/m) || [])[1]
  const sk = (out.match(/^SK=(\S+)$/m) || [])[1]
  if (!pk || !sk) throw new Error(`生成 Falcon 密钥对失败：${out.slice(0, 300)}`)
  return { publicKey: pk, privateKey: sk }
}

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：先证明**跑着的服务端**有回收入口，再谈它做得对不对
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：回收入口到底在不在跑着的进程里')

// 探法用**无令牌**请求：新端点没注册时拿到的是 404/405，注册了则是 401
// （`require_kms_user` 先于路由处理逻辑拦下）。401 ∉ {404, 405}，
// 所以"不是 404/405"就等价于"这个路由存在"。
//
// 为什么不用"带令牌调一次"来探：那要么真的撤掉一把密钥（探针有副作用，
// 不能安全地跑在任何用例之前），要么用非法参数换取 INVALID_PARAMETER ——
// 后者其实也行，但它把"端点没部署"与"参数校验没写"混在一条断言里，
// 而这两件事的处置完全不同。
const probe = await api(PQKDS, '/node-self/keys/revoke/', {
  method: 'POST',
  body: { algorithm: KYBER, keyId: 'probe-not-a-real-key', keyVersion: 1 }
})
const probeOk = probe.status !== 404 && probe.status !== 405
check('★ 回收入口已部署（不是 404/405）', probeOk,
  `HTTP=${probe.status} body=${JSON.stringify(probe.body).slice(0, 120)}`)
if (!probeOk) {
  info('端点没注册：后面的用例一条都不跑 —— 否则每条断言都会以"没读到字段"的')
  info('方式失败，看起来像十几个逻辑缺陷，实际只是一次部署问题。')
  info('先重建后端镜像（代码是打进镜像的，docker cp 之后进程不重启就 import 不到），再重跑。')
  finish()
  process.exit(1)
}

// ---------------------------------------------------------------------------
// 2. 准备：两个真节点，四套密钥登记齐
// ---------------------------------------------------------------------------
title('2. 准备：两个真节点（发送方 A / 被回收方 B）')
// ⚠️ `adminLogin()` 返回的是**裸令牌字符串**（`tools/lib/captcha.mjs` 的
//    `login()` 末尾就是 `return json.token`），**不是** `{token}` 对象。
//    写成 `admin.token` 会静默拿到 `undefined`：`api()` 的 `...(token ? {...})`
//    于是**一个 Authorization 头都不带**，服务端回一句"未登录：缺少
//    Authorization"，看起来像"令牌过期/权限不够"，而真相是本地变量取空了。
//    `createNode` 之所以没暴露它，是因为它整个把字符串当 token 传（参数名就叫
//    adminToken）——同一次登录，一半调用能用、一半不能用。
const adminToken = await adminLogin()
const nodeA = await newNodeSession(adminToken, { prefix: 'KRA', name: 'KMS-007 回收（发送方）', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'KRB', name: 'KMS-007 回收（被回收方）', domainId: DOMAIN })
check('两个节点都已激活（各自持有登录令牌）',
  Boolean(nodeA.token && nodeB.token && nodeA.nodeId !== nodeB.nodeId),
  `A=${nodeA.nodeId} B=${nodeB.nodeId}`)

const dbIdOf = (nodeId) => sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeId}';`) || ''
const sysUserOf = (nodeId) => sqlScalar(`SELECT IFNULL(sys_user_id, '') FROM ${NODE_TABLE} WHERE node_id='${nodeId}';`) || ''
const nodeAId = dbIdOf(nodeA.nodeId)
const nodeBId = dbIdOf(nodeB.nodeId)
const userA = sysUserOf(nodeA.nodeId)
check('两个节点在库里有主键、且都映射到了用户（回收与分发的身份都靠它）',
  Boolean(nodeAId && nodeBId && userA), `A.pk=${nodeAId} B.pk=${nodeBId} A.user=${userA}`)

// 两个节点都要在**回收前**拿到完整的四套公钥：第 5/8 节撤 B 的 KYBER、
// 第 6 节撤 A 的 FALCON，都要求那一行先是 ACTIVE（否则 `wasActive=true`
// 那条断言测的就不是"撤掉了生产版本"）。四套一起登记也顺带覆盖了
// store_node_public_key 的四个算法分支。
info('生成四套密钥并登记（FALCON 本机生成要十几秒，两遍）…')
const keys = {}
for (const [label, session] of [['A', nodeA], ['B', nodeB]]) {
  keys[label] = {}
  for (const [algorithm, options, extra] of [
    ['SM2', {}, {}],
    ['SSCL', {}, {}],
    [KYBER, { variant: VARIANT }, { securityLevel: String(VARIANT) }],
    [FALCON, {}, {}]
  ]) {
    const material = await cryptoProvider.generate(algorithm, { nodeId: session.nodeId, ...options })
    const up = await register(session, algorithm, material, extra)
    if (!isOk(up.body)) {
      check(`${label} 的 ${algorithm} 登记成功`, false, `code=${up.body?.code} msg=${up.body?.msg}`)
    }
    keys[label][algorithm] = material
  }
}
check('两个节点各自四套密钥都已登记且为 ACTIVE',
  [nodeA, nodeB].every((s) => [KYBER, FALCON, 'SM2', 'SSCL'].every(
    (alg) => String(ltKeyFact(s.nodeId, alg, keys[s === nodeA ? 'A' : 'B'][alg].keyId, 1)).includes('|ACTIVE|'))),
  `${nodeA.nodeId} / ${nodeB.nodeId}`)
info('⚠️ 四套都复核，不只看 KYBER/FALCON —— 断言面与名字一致，别让 SM2/SSCL 只有'
  + '"登记没报错"这一层证据。')

// 初始化收尾（幂等）：它只校验四套公钥齐备后把节点置为 ACTIVE，不再生成密钥。
for (const session of [nodeA, nodeB]) {
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
  check(`${session.nodeId} 初始化收尾成功`, isOk(init.body), `code=${init.body?.code} msg=${init.body?.msg}`)
}

// 第二次探针：这次带上令牌，用一个**服务端读不懂的版本号**。
// 它与上一条探的不是同一件事：上一条探"路由在不在"，这一条探"参数校验在不在"
// （`True` 在 Python 里 `int()` 收成 1，静默变成"撤 v1" —— 而那可能正是在产的
// 那一版，且响应照常成功）。这条不碰库：版本解析排在查行之前。
const probe2 = await revoke(nodeA, KYBER, 'probe-not-a-real-key', true, '部署探针')
check('★ 服务端读不懂的版本号必须被拒（证明参数校验这段代码真的在跑）',
  probe2.body?.data?.error_code === 'INVALID_PARAMETER',
  `code=${probe2.body?.code} ${errCodeOf(probe2.body)} —— 若被"接受"，说明容器跑的是旧代码`)

// ---------------------------------------------------------------------------
// 3. 回收前的基线：造出「已有会话」与「发得出去的信封」
// ---------------------------------------------------------------------------
title('3. 基线：回收前这套链路是通的（否则第 5 节的"被拒"说明不了任何事）')
info('顺序：给 A 授权 B → 在 KMS 侧建一把用户密钥 → A 向 B 分发一次。')
info('分发是**节点腿（抗量子）+ 用户腿（信封）**一起做的，节点腿会为成功的节点建一条 initiated 会话。')

// ⚠️ 授权这一步不能省：`_validate_request` 里 `_authorized_node_ids` 会对
//    未授权的节点返回 403。`node_ids` 是 **Node 的主键**，不是业务编号。
const grant = await api(PQKDS, '/admin/node-authorizations/', {
  method: 'POST',
  token: adminToken,
  body: { userId: Number(userA), nodeId: Number(nodeBId), remark: 'KMS-007 验收：A 需要能向 B 分发' }
})
check('节点鉴权已授予（A 的用户 → B 的节点）', isOk(grant.body),
  `code=${grant.body?.code} msg=${grant.body?.msg}`)

// 用户腿的源密钥来自主 KMS 的 `kms.keymanage` —— 不是 pqkds 侧的长期密钥表。
// 它与节点腿是两条独立的路，KMS-007 只管节点腿那一半（见文档 §4.0 D5）。
const km = await api(UPDATEDEL_API, '/lifecycle/keymanage', {
  method: 'POST',
  token: adminToken,
  body: {
    userId: Number(userA),
    userName: nodeA.nodeId,
    encrytType: '无证书非对称加密',
    encrytName: 'SM2',
    keyName: `KMS-007 验收 ${Date.now()}`,
    keyUse: 'session',
    keyDomain: 'A',
    status: '0',
    ua: UA
  }
})
const sourceKeyId = km.body?.data?.key_id ?? km.body?.data?.keyId
check('用户腿源密钥已建立（后面两次分发都用它）', Boolean(sourceKeyId),
  `HTTP=${km.status} key_id=${sourceKeyId} msg=${km.body?.message || km.body?.msg}`)

// ⚠️ 用**A 自己的令牌**调：`sender_node` 是从令牌自省出的用户经 `Node.sys_user_id`
//    反查来的，请求体里没有它的位置。换成管理员令牌会得到"发起用户未映射到节点"。
const distPre = await api(PQKDS, '/key-pool/distribute-to-user/', {
  method: 'POST',
  token: nodeA.token,
  body: { source_key_id: Number(sourceKeyId), node_ids: [Number(nodeBId)], count: 1, node_wrapping_algorithm: 'kyber_kem' }
})
check('★ 回收前：分发给 B 是成功的（这条基线不成立的话，第 5 节的"被拒"可能只是参数写错）',
  isOk(distPre.body) && distPre.body?.data?.status === 'success'
  && (distPre.body?.data?.failed || []).length === 0,
  `code=${distPre.body?.code} status=${distPre.body?.data?.status} failed=${JSON.stringify(distPre.body?.data?.failed)}`)
check('节点腿确实交付到了 B（delivered=true）',
  (distPre.body?.data?.nodeResults || []).some((r) => r.nodeCode === nodeB.nodeId && r.delivered === true),
  JSON.stringify(distPre.body?.data?.nodeResults))

const preBatchId = distPre.body?.data?.batchId || ''
// ⚠️ 按**本次批次号**查会话，不查"最新一行"：库里到处是历史会话，取最新那条
//    会在"这一批没建会话"时照样拿到一行，于是用例静默通过。
const preSession = sqlScalar(
  `SELECT session_id FROM ${SESSION_TABLE} WHERE session_id LIKE '${preBatchId}-%' ORDER BY id DESC LIMIT 1;`
) || ''
check('★ 这一批真的建出了会话，且状态是 initiated（分发只建 initiated，不建 established）',
  Boolean(preSession) && sessionStatus(preSession) === 'initiated',
  `session_id=${preSession} status=${sessionStatus(preSession)}`)

// ---------------------------------------------------------------------------
// 3.5 ★ 正对照：① 取信封 与 ④ 线上预分配 —— 回收**之前**必须成功
// ---------------------------------------------------------------------------
title('3.5 ★ 正对照：① 与 ④ 两条闸门在回收前是放行的')
info('复核指出：这两条闸门在旧脚本里**从未在回收前成功调用过**，所以一条')
info('"闸门永远拒绝"的回归会让 §5.1 的两条断言全绿。这里各成功跑一次，')
info('把"放行"与"拒绝"配成一对 —— 只有这样，§5.1 的拒绝才说明是回收导致的。')

// ① GET /node-self/envelopes/：§3 刚给 B 发过信封，此刻它应当能取到。
const epPos = await api(PQKDS, '/node-self/envelopes/', { token: nodeB.token })
check('① 正对照：回收前 B 能取到信封（HTTP 200 + code 200 + items 非空）',
  epPos.status === 200 && isOk(epPos.body) && Number(epPos.body?.data?.total) >= 1,
  `HTTP=${epPos.status} code=${epPos.body?.code} total=${epPos.body?.data?.total}`
  + ` ${epPos.body?.data?.error_code || ''}`)

// ④ POST /key-pool/distribute/：闸门在**发送方**（判 sender 的 KYBER）。
//    此刻 A 的 KYBER 是好的，所以这一次必须先成功 —— §5.1 里那次让它当 sender
//    时被拒，撤的却是 B 的密钥，两次的差别只有"B 的密钥还在不在"。
//    ⚠️ count 显式给 1：缺省是 50，白造 50 条池项。
const ep4Pos = await api(PQKDS, '/key-pool/distribute/', {
  method: 'POST',
  body: { sender_node_id: nodeA.nodeId, receiver_node_id: nodeB.nodeId, count: 1 }
})
check('④ 正对照：回收前 A→B 的线上预分配成功（闸门在发送方，此刻它是好的）',
  ep4Pos.status === 200 && isOk(ep4Pos.body) && Number(ep4Pos.body?.data?.generated) >= 1,
  `HTTP=${ep4Pos.status} code=${ep4Pos.body?.code} generated=${ep4Pos.body?.data?.generated}`
  + ` msg=${ep4Pos.body?.msg}`)

// ---------------------------------------------------------------------------
// 3.6 ★ 正对照：⑤ 签名闸门 —— 给它一把**真** Falcon 私钥，证明放行分支真在签名
// ---------------------------------------------------------------------------
title('3.6 ★ 正对照：⑤ 签名闸门放行时会真的签名（不是"已登记就能过"）')
info('这道闸门有两条分支：登记表说不可用 → 拒绝（§6 测）；可用 → 照常签名。')
info('旧脚本从没跑过放行分支，于是"这条路径其实没接上"与"接了但永远拒绝"分不出来。')
info('做法：种一把真 Falcon-512 私钥进 falcon_sign_private_key，分发一次，')
info('然后在**库内**核对那封信封确实带上了签名，并让服务端自己验一次。')

// ⚠️ 只种私钥列，**不动** `falcon_sign_public_key`：分发路径只读私钥列
//    （公钥列是 `distribution-batches` 查询接口验签用的）。改了公钥列会让
//    "物化列与登记行一致"这条既有不变量出现一处人造的破口，而本用例并不需要它。
// ⚠️ 种真密钥而不是垃圾：`sign_envelope` 会先 base64 解码、再比对 1281 字节长度，
//    最后交给 DLL 真签一次；喂 `'00'` 会在第一步就返回 None —— 信封没有签名，
//    而那与"放行分支没接上"在断言上无法区分。
const falconPair = generateFalconKeypair()
sqlScalar(`UPDATE ${NODE_TABLE} SET falcon_sign_private_key='${falconPair.privateKey}' WHERE node_id='${nodeA.nodeId}';`)
check('⑤ 正对照：已在本机种入一把真 Falcon-512 私钥（1281 字节 → base64 后约 1708 字符）',
  falconPair.privateKey.length > 1000,
  `privateKey 长度=${falconPair.privateKey.length}`)

const distSigned = await api(PQKDS, '/key-pool/distribute-to-user/', {
  method: 'POST',
  token: nodeA.token,
  body: { source_key_id: Number(sourceKeyId), node_ids: [Number(nodeBId)], count: 1, node_wrapping_algorithm: 'kyber_kem' }
})
check('⑤ 正对照：带真私钥的分发整体成功（闸门放行，不是"有私钥就拒"）',
  isOk(distSigned.body) && distSigned.body?.data?.status === 'success',
  `code=${distSigned.body?.code} status=${distSigned.body?.data?.status} failed=${JSON.stringify(distSigned.body?.data?.failed)}`)

const signedBatchId = distSigned.body?.data?.batchId || ''
// ⚠️ 签名写在**用户腿信封**（`UserKeyEnvelope`）里，不是节点腿的池行：
//    代码里 `user_envelope['signature'] = _sig` 只落在信封那条记录上。
//    去池行找 `"signature"` 会恒为 NO_SIG —— 探针实测过这个岔路。
const envelopeHasSig = sqlScalar(
  `SELECT IF(encrypted_key_data LIKE '%"signature"%', 'HAS_SIG', 'NO_SIG') `
  + `FROM ${ENVELOPE_TABLE} WHERE batch_id='${signedBatchId}' LIMIT 1;`
) || ''
// ⚠️ 这里**只断言"签名被写出来了"**，不追加"验得过" —— 因为现在验不过，
//    而且那是一个**与回收无关的既有断口**（写这份时的实测结论）：
//
//      签名覆盖 `envelope_signature.SIGNED_FIELDS`（batch_id / wrapping_algorithm /
//      payload_algorithm / recipient_user_id / ciphertext_digest / source_key_id /
//      expires_at），但落库的 `user_envelope` 里**只有 ciphertext_digest 与
//      payload_algorithm** —— 另外五个字段从没写进去。验签侧
//      `_verify_envelope_signature` 从库里重建被签字节串时，它们全是 `None`，
//      于是「自己签的信，自己验不过」。
//
//    影响面：`GET /user-symmetric-keys/<id>/` 在交出密文前先验签，
//    验不过时返回 403「信封验签失败，拒绝交出密文」—— 也就是**用户腿的信封
//    当前取不到密文**。签名写入那一步本身是对的（`HAS_SIG` 这条能过），
//    坏在"被签的字段没有随信封一起落库"。
//
//    为什么不在这里修：它不在 KMS-007 的改动面上（KMS-007 是回收影响处理），
//    且修它要决定"信封里该冗余存哪些字段"这类契约问题（KMS-010 的信封登记
//    与 KMS-011 的取信封才是那条线）。这里如实记录，不掩盖也不越界。
//    追它的最小复现：本脚本 §3.6 那条 `HAS_SIG` 之后再查一次
//    `batch_id` 是否为 null —— 是 null 就说明本注释描述的断口仍在。
const signedEnvFields = sqlScalar(
  `SELECT CONCAT_WS('|', IF(encrypted_key_data LIKE '%"batch_id"%', 'BATCH', 'NO_BATCH'), `
  + `IF(encrypted_key_data LIKE '%"source_key_id"%', 'SRC', 'NO_SRC')) `
  + `FROM ${ENVELOPE_TABLE} WHERE batch_id='${signedBatchId}' LIMIT 1;`
) || ''
check('⑤ 正对照：签名**写出去了**（放行分支真的走到底了，与"没接上"可区分）',
  Boolean(signedBatchId) && envelopeHasSig === 'HAS_SIG',
  `batchId=${signedBatchId} 信封=${envelopeHasSig}`)
check('⚠️ 既有断口（如实记录，非本次修复面）：落库的信封里**没有**被签的字段',
  signedEnvFields === 'NO_BATCH|NO_SRC',
  `落库字段=${signedEnvFields} —— 若变成 BATCH|SRC，说明该断口已被 KMS-010/011 修掉，`
  + '本节注释与下面那条"验不过"的说明应当一并更新')

// 再让服务端自己验一次 —— 但它现在**必然验不过**，所以这里的断言方向是反的：
// 断言"验不过"，并把原因钉住（被签字段缺失）。这样做的价值在于：
//   * 若哪天有人把字段补上，这条**立刻红**，提醒去更新上面那段说明；
//   * 若哪天验签逻辑被改坏成"永远返回 False"，这条**照样绿** —— 所以它单独
//     不足以证明验签实现是对的，它的作用只是把断口的存在与原因写进证据里。
// 同时用**两个**视角各验一次，把"签名本身是好的"与"重建不出被签内容"分开：
//   A) 拿**签名时同一份** `envelope_for_sign` 的字段值（在本进程里重建）→ 应当 True
//   B) 拿**库里存下来的**信封重建 → 应当 False（缺五个字段）
// 两条合起来才说明：签名的密码学是对的，坏的是"字段没随信封落库"。
const verifyProgram = `
import json, sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django; django.setup()
from pqkds.models import UserKeyEnvelope, Node
from pqkds.envelope_signature import verify_envelope, SIGNED_FIELDS

env = UserKeyEnvelope.objects.filter(batch_id='${signedBatchId}').first()
payload = json.loads(env.encrypted_key_data or '{}')
pub = '${falconPair.publicKey}'
sig = payload.get('signature')
print('SIG_PRESENT=%s' % bool(sig))
# B) 库里存下来的字段（缺 batch_id/source_key_id/... → 重建不出被签串）
stored_view = {k: payload.get(k) for k in SIGNED_FIELDS}
print('MISSING_FIELDS=%s' % ','.join(k for k in SIGNED_FIELDS if stored_view.get(k) is None))
print('STORED_VERIFY=%s' % verify_envelope(stored_view, sig, pub))
# A) 用**数据库列**里记着的那些值重建（batch_id/source_key_id/expires_at 都在列上，
#    不在 JSON 里）—— 验得过就证明签名本身有效、签的确实是这些值。
row_view = dict(stored_view)
row_view['batch_id'] = env.batch_id
row_view['source_key_id'] = env.source_key_id
row_view['wrapping_algorithm'] = env.wrapping_algorithm
row_view['expires_at'] = env.expires_at.isoformat() if env.expires_at else None
# 签名时叫 recipient_user_id，落库列叫 user_id —— 同一个值的两个名字。
# 一开始漏了这条映射，ROW_VERIFY 仍是 False，看起来像"签名坏了"，
# 实际是这个字段没填。
row_view['recipient_user_id'] = env.user_id
print('ROW_VERIFY=%s' % verify_envelope(row_view, sig, pub))
`
const verifyOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: verifyProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
const sigLines = verifyOut.trim().split('\n').filter((l) => /^[A-Z_]+=/.test(l)).join(' ')
check('⑤ 正对照：签名**确实写出去了**（`HAS_SIG` 之外，再从库里解析一次确认）',
  verifyOut.includes('SIG_PRESENT=True'), sigLines)
check('★ ⑤ 正对照：签名本身**是有效的**（用落库值重建被签串 → 验得过）',
  verifyOut.includes('ROW_VERIFY=True'),
  sigLines + ' —— ROW_VERIFY=False 意味着连"签名与这些值匹配"都不成立，'
  + '那会是比"字段没落库"更严重的问题')
check('⚠️ 既有断口复现：拿**库里信封**重建被签串时验不过，且缺的正是那五个字段',
  verifyOut.includes('STORED_VERIFY=False') && verifyOut.includes('MISSING_FIELDS=')
  && /MISSING_FIELDS=(?!\s*$)./.test(verifyOut),
  sigLines)

// ---------------------------------------------------------------------------
// 3.7 ★ 反例哨兵：一条**无关节点对**的活跃会话，回收全程都不该被碰
// ---------------------------------------------------------------------------
title('3.7 ★ 反例哨兵：无关节点对（C↔D）的活跃会话必须全程保持 active')
info('复核指出：夹具里只有 (A,B) 一条会话，所以"过度失效"（把不该撤的也撤了）')
info('与正确实现都满足 `sessions >= 1` —— 上界那一半完全没有证据。')
info('这里另建一对**不参与任何回收**的节点 C/D，插一条活跃会话当哨兵：')
info('只要吊销逻辑从"按节点匹配"退化成"扫全表"，它就会翻成 revoked。')

const nodeC = await newNodeSession(adminToken, { prefix: 'KRC', name: 'KMS-007 哨兵 C', domainId: DOMAIN })
const nodeD = await newNodeSession(adminToken, { prefix: 'KRD', name: 'KMS-007 哨兵 D', domainId: DOMAIN })
const nodeCId = dbIdOf(nodeC.nodeId)
const nodeDId = dbIdOf(nodeD.nodeId)
check('哨兵节点 C/D 已建好并激活（它们的密钥一把都不会被回收）',
  Boolean(nodeC.token && nodeD.token && nodeCId && nodeDId),
  `C=${nodeC.nodeId}(pk=${nodeCId}) D=${nodeD.nodeId}(pk=${nodeDId})`)

const sentinelSession = `KMS007-SENTINEL-${Date.now()}-CD`
// ⚠️ 直接 INSERT 而不是走分发接口：走真实分发要给 C/D 各生成并登记密钥、
//    再做一次封装，成本与"这条会话会不会被误撤"无关。哨兵要的只是
//    "一条落在无关节点对上的、状态在失效扫描范围内的行"。
//    状态取 `initiated` —— 它正是 `invalidate_sessions_for_node_key_update`
//    会扫的三个状态之一，所以"过度失效"一旦发生，它必然中招。
sqlScalar(
  `INSERT INTO ${SESSION_TABLE} `
  + `(session_id, node1_id, node2_id, encrypted_session_key, key_exchange_data, `
  + ` session_type, status, expires_at, create_datetime) `
  + `VALUES ('${sentinelSession}', ${nodeCId}, ${nodeDId}, 'see envelopes of batch sentinel', `
  + `'{"batch_id":"sentinel","dispatch":"kms007-fixture"}', 'kyber_kem', 'initiated', `
  + `DATE_ADD(NOW(), INTERVAL 24 HOUR), NOW());`
)
check('★ 哨兵会话已就位且初始为 initiated（它不在失效扫描范围之外，才测得出过度失效）',
  sessionStatus(sentinelSession) === 'initiated',
  `session_id=${sentinelSession} status=${sessionStatus(sentinelSession)}`)

// ---------------------------------------------------------------------------
// 4. 影响面夹具：三个池子 —— 另一个 keyId + 同 keyId 的两个版本
// ---------------------------------------------------------------------------
title('4. 影响面夹具：三个 kyber 池子（把"精确失效"的两个维度分开钉）')
info('池项在**生成时**回填「消费方（node2）那把长期密钥」的 keyId + 版本（D3）。')
info('所以让 B 的 KYBER 先换 keyId、再升一版，每换一次生成一个池子 —— 三个池子')
info('分别引用 K1/v1、K2/v1、K2/v2。第 5 节撤 K2/v2：只有第三个该灭，')
info('前两个（另一个 keyId、同一个 keyId 的老版本）都必须原封不动。')
info('（这里刻意不造 FALCON 池：generate_falcon_pool 对当前登记链路是死的，')
info('  恒回 generated=0，拿它当对照只会空洞地通过 —— 详见文件头的说明。）')

// ⚠️ count 必须显式给：接口缺省是 50 条，白造一百条池项只会让开发库变脏。
//    ⚠️ 不传令牌：`KeyPoolViewSet.get_permissions` 返回空列表，这个命名空间本来就不鉴权。
const kyberGen = (count) => api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId, algorithm: 'kyber_kem', count }
})

/** §2 登记的那把，此刻是 B 的 KYBER 生产版本 —— 第一个池子引用它。 */
const K1 = keys.B[KYBER]
const genP1 = await kyberGen(2)
const poolK1 = genP1.body?.data?.pool_id || ''

// 换一个 keyId 登记（**不带** rotate）：B 的 KYBER 生产槽位转到 K2/v1。
const K2 = await cryptoProvider.generate(KYBER, { nodeId: nodeB.nodeId, variant: VARIANT })
const K2Up = await register(nodeB, KYBER, K2, { securityLevel: String(VARIANT) })
check('B 登记第二把 KYBER（新 keyId）成功，并接管生产槽位',
  isOk(K2Up.body) && K2.keyId !== K1.keyId,
  `code=${K2Up.body?.code} msg=${K2Up.body?.msg} K1=${K1.keyId} K2=${K2.keyId}`)

const genP2 = await kyberGen(2)
const poolK2v1 = genP2.body?.data?.pool_id || ''

// 同一个 keyId 升到 v2（走更新页那条 rotate 语义）：K2/v1 降级 RETIRED，K2/v2 接槽位。
const K2v2 = await cryptoProvider.generate(KYBER, {
  nodeId: nodeB.nodeId, keyId: K2.keyId, version: Number(K2.version) + 1, variant: VARIANT
})
const K2v2Up = await register(nodeB, KYBER, K2v2, { securityLevel: String(VARIANT), rotate: true })
check('B 把同一个 keyId 更新到 v2 成功（这一版才是第 5 节的回收目标）',
  isOk(K2v2Up.body) && String(K2v2Up.body?.msg || '').includes('已更新'),
  `code=${K2v2Up.body?.code} msg=${K2v2Up.body?.msg}`)

const genP3 = await kyberGen(3)
const poolK2v2 = genP3.body?.data?.pool_id || ''

for (const [label, gen] of [['poolK1（引用 K1/v1）', genP1], ['poolK2v1（引用 K2/v1）', genP2], ['poolK2v2（引用 K2/v2）', genP3]]) {
  check(`${label} 已生成`, isOk(gen.body) && Number(gen.body?.data?.generated) >= 1,
    `code=${gen.body?.code} msg=${gen.body?.msg} generated=${gen.body?.data?.generated}`)
}
check('★ 三个池子分别记着 K1/v1、K2/v1、K2/v2（引用不是"随便哪个"—— 否则下面的断言退化成按节点全清，测不出东西）',
  poolKeyRef(poolK1, 'kyber_kem') === `${K1.keyId}|1`
  && poolKeyRef(poolK2v1, 'kyber_kem') === `${K2.keyId}|1`
  && poolKeyRef(poolK2v2, 'kyber_kem') === `${K2.keyId}|2`,
  `K1池=${poolKeyRef(poolK1, 'kyber_kem')} K2v1池=${poolKeyRef(poolK2v1, 'kyber_kem')} K2v2池=${poolKeyRef(poolK2v2, 'kyber_kem')}`)

const k1Ready = poolCounts(poolK1).ready
const k2v1Ready = poolCounts(poolK2v1).ready
const k2v2Ready = poolCounts(poolK2v2).ready
check('三个池子的 READY 数都 > 0（空池会让下面"必须还活着"的断言空洞地通过）',
  k1Ready > 0 && k2v1Ready > 0 && k2v2Ready > 0,
  `poolK1=${k1Ready} poolK2v1=${k2v1Ready} poolK2v2=${k2v2Ready}`)
info(`poolK1 READY=${k1Ready}，poolK2v1 READY=${k2v1Ready}，poolK2v2 READY=${k2v2Ready}`)

// ---------------------------------------------------------------------------
// 5. ★ 判据③④：回收 B 的 KYBER（K2/v2，在产版）
// ---------------------------------------------------------------------------
title('5. ★ 回收 B 的 KYBER（K2/v2）：四个入口 + 影响面 + 审计与链上')

const B_KYBER_REASON = 'KMS-007 验收：回收后四个入口都要报 KEY_REVOKED'

// ⚠️ 必须在**回收之前**数：(A,B) 这条边上的活跃会话，回收后按它断言。
//    硬编码条数会随夹具增删而失效（§3 基线 + §3.6 签名分发各建了一条），
//    所以按"回收前实际存在几条"来判 —— 要紧的是**只撤不增**，不是具体数字。
// ⚠️ 用 node 的**整数主键**过滤（node1_id/node2_id），不是业务编号：
//    后者是字符串列，与整数列比较恒不命中却不报错。
const activeSessionsOnAB = () => Number(sqlScalar(
  `SELECT COUNT(*) FROM ${SESSION_TABLE} `
  + `WHERE status IN ('initiated','established','blockchain_recorded') `
  + `AND ((node1_id=${ownerId(nodeA.nodeId)} AND node2_id=${ownerId(nodeB.nodeId)}) `
  + `  OR (node1_id=${ownerId(nodeB.nodeId)} AND node2_id=${ownerId(nodeA.nodeId)}));`
) || 0)
const abActiveBefore = activeSessionsOnAB()
check('回收前 (A,B) 上确有活跃会话（否则下面"全被撤掉"在空集合上空洞成立）',
  abActiveBefore >= 1, `(A,B) 活跃会话=${abActiveBefore} 条`)

const revB = await revoke(nodeB, KYBER, K2v2.keyId, K2v2.version, B_KYBER_REASON)
const revBData = revB.body?.data || {}
check('回收请求成功（HTTP 200 + code 200）',
  revB.status === 200 && isOk(revB.body), `HTTP=${revB.status} code=${revB.body?.code} msg=${revB.body?.msg}`)

// 链上回读要用这两条**独立**事实（不是从响应里取的）：
//   * `rowId` —— 那一行 `NodeLongTermKey` 的整数主键，正是上链时传的 keyId。
//     取响应里的 `revoked.rowId` 也行，但它与"链上写对了吗"是同一个来源；
//     这里直接查库，让"链上 keyId" 与"库里那一行"对得上，绕开响应。
//   * `public_key_hash` —— 上链传的摘要，同样从库里读。
const k2v2RowId = sqlScalar(
  `SELECT id FROM ${LTK_TABLE} WHERE node_id=${ownerId(nodeB.nodeId)} `
  + `AND algorithm='${KYBER}' AND key_id='${K2v2.keyId}' AND key_version=2;`
) || ''
const k2v2Hash = sqlScalar(
  `SELECT IFNULL(public_key_hash, '') FROM ${LTK_TABLE} WHERE id=${k2v2RowId};`
) || ''
check('链上回读的比对基准已从**库里**取到（不是从响应里抄的）',
  Boolean(k2v2RowId) && Boolean(k2v2Hash),
  `rowId=${k2v2RowId} hash=${String(k2v2Hash).slice(0, 24)}…（响应里报的是 rowId=${revBData.revoked?.rowId}）`)
check('★ 撤的正是生产版本：wasActive=true 且 alreadyRevoked=false',
  revBData.revoked?.wasActive === true && revBData.revoked?.alreadyRevoked === false,
  JSON.stringify(revBData.revoked))
check('库内已是 REVOKED 终态',
  String(ltKeyFact(nodeB.nodeId, KYBER, K2v2.keyId, 2)).includes('|REVOKED|'),
  String(ltKeyFact(nodeB.nodeId, KYBER, K2v2.keyId, 2)))
check('★ 回收同时清空物化列（不清的话既有读路径会继续把已回收的公钥当可用，且失败是静默的）',
  nodeColumnIs(nodeB.nodeId, 'kyber_public_key', ''),
  '期望 Node.kyber_public_key 为空')

// --- 判据④ 库内那一半 -----------------------------------------------------
check('★ 判据④（库内）：回收原因与回收时间都落在那一行上',
  ltRevoked(nodeB.nodeId, KYBER, K2v2.keyId, 2) === `${B_KYBER_REASON}|SET`,
  `读到 ${ltRevoked(nodeB.nodeId, KYBER, K2v2.keyId, 2)}`)

// --- 影响面 ---------------------------------------------------------------
const k2v2After = poolCounts(poolK2v2)
const k2v1After = poolCounts(poolK2v1)
const k1After = poolCounts(poolK1)
check('★ 影响面如实回报：池项数 = 库里这个池子此前 READY 的条数（精确到条）',
  revBData.impact?.poolItems === k2v2Ready,
  `响应 ${revBData.impact?.poolItems}，库里回收前 READY=${k2v2Ready}`)
check('★ 目标池项全部转入 REVOKED',
  k2v2After.revoked === k2v2Ready && k2v2After.ready === 0,
  `${JSON.stringify(k2v2After)}`)
check('★★ 同一个 keyId 的**老版本**（K2/v1）的池项必须还活着 —— 只按 keyId 匹配的实现会把它一起撤掉',
  k2v1After.ready === k2v1Ready && k2v1After.revoked === 0,
  `${JSON.stringify(k2v1After)}（钉的是精确匹配的版本维）`)
check('★★ 另一个 keyId（K1/v1）的池项也必须还活着 —— 改前只按 node 全清，它会连自己一起撤',
  k1After.ready === k1Ready && k1After.revoked === 0,
  `${JSON.stringify(k1After)}（钉的是 revoke_pool_items_for_key 改前的缺陷）`)
check('★ 会话被连带撤销：目标会话 revoked，且 (A,B) 上的活跃会话**全部**转 revoked、条数恰好等于回收前',
  sessionStatus(preSession) === 'revoked'
  && Number(revBData.impact?.sessions) === abActiveBefore
  && revBData.impact?.sessionsOk === true
  && activeSessionsOnAB() === 0,
  `会话=${sessionStatus(preSession)} 影响面 sessions=${revBData.impact?.sessions}`
  + `（回收前 (A,B) 活跃=${abActiveBefore}）ok=${revBData.impact?.sessionsOk}`
  + ` 回收后 (A,B) 活跃=${activeSessionsOnAB()}`
  + ' —— 影响面数必须等于回收前活跃数：报少了是漏撤，报多了是把别人撤了')
check('★★ 反例哨兵：无关节点对（C↔D）的活跃会话**全程未被碰**（过度失效的哨兵）',
  sessionStatus(sentinelSession) === 'initiated',
  `哨兵=${sessionStatus(sentinelSession)}（期望 initiated）—— 若为 revoked，`
  + '说明吊销从"按节点匹配"退化成"扫全表"，而旧脚本的 sessions>=1 抓不到')
check('★★ 哨兵没有被写进任何失效记录（不是"状态没改但记了一笔"）',
  invalidationCount(sentinelSession) === 0,
  `哨兵失效记录数=${invalidationCount(sentinelSession)}`)
check('★ 失效记录写的是已声明的 manual_revocation，且指向触发节点 B（不是新造的第三个值）',
  invalidationFact(preSession) === `manual_revocation|${nodeBId}`,
  `读到 ${invalidationFact(preSession)}，期望 manual_revocation|${nodeBId}`)

// --- 判据④ 链上那一半（与库内**分开**读，且**不靠响应自证**）-----------------
const chainHash = String(revBData.chainHash || '')
check('★ 判据④（链上）：本次回收带回链上交易哈希（非空）', Boolean(chainHash), chainHash || '（空）')
info('链上事件按设计**不落库表**：它不写 key_operation_record、也不动 keymanage.chain_status，')
info('在 MySQL 里没有可回读的行。所以"已上链"只能去链上读 —— 下面直接读全链。')

// ⚠️ 这一段是复核点名的核心空洞：`Boolean(chainHash)` 只证明"回执里解出了至少
//    一个 KeyLifecycleEvent"。`eventType` 写成 KEY_UPDATED、keyId/版本/节点写错，
//    哈希照回，那条断言照样绿。要证伪就得**读链**，逐字段比对。
//
// ⚠️ 一次全链扫描、两个用例用：§5 读"这次回收的事件内容"，§8 读"重试后条数不变"。
//    中间不再扫 —— 两次扫描之间没有别的写链动作，而扫描要遍历每个块。
const eventsAfterRevoke = await scanLifecycleEvents()
const revEvents = revokedEventsFor(eventsAfterRevoke, k2v2RowId, nodeB.nodeId)
const revEvent = revEvents[0]
check('★ 判据④（链上回读）：按交易哈希读出的事件**就是** KEY_REVOKED',
  Boolean(revEvent) && revEvent.txHash === chainHash,
  revEvent ? `tx=${revEvent.txHash} eventType=${revEvent.eventType}`
    : `链上找不到 tx=${chainHash} 对应的 KEY_REVOKED 事件`
      + `（扫描了 ${eventsAfterRevoke.length} 条生命周期事件）`)
check('★★ 链上事件的 keyId = 那一行的整数主键（不是字符串 key_id "KRB-…"）',
  Boolean(revEvent) && revEvent.keyId === BigInt(k2v2RowId),
  revEvent ? `链上 keyId=${revEvent.keyId} 库里 rowId=${k2v2RowId}（字符串 key_id=${K2v2.keyId}）` : '（无事件）')
check('★★ 链上事件的版本 = 被撤的那一版（v2），不是 0 也不是别的版本',
  Boolean(revEvent) && revEvent.version === 2,
  revEvent ? `链上 version=${revEvent.version}` : '（无事件）')
check('★★ 链上事件的 nodeId = 被撤方 B（链上接口只收非空 nodeId，写错就无从追溯）',
  Boolean(revEvent) && revEvent.nodeId === nodeB.nodeId,
  revEvent ? `链上 nodeId=${revEvent.nodeId}，期望 ${nodeB.nodeId}` : '（无事件）')
check('★★ 链上事件的公开材料摘要 = 库里那一行的 public_key_hash（逐字）',
  Boolean(revEvent) && revEvent.materialHash === k2v2Hash,
  revEvent ? `链上=${revEvent.materialHash.slice(0, 24)}… 库内=${String(k2v2Hash).slice(0, 24)}…` : '（无事件）')
check('★ 链上事件确实来自被部署的那个合约（地址不是别处）',
  Boolean(revEvent) && revEvent.contract.toLowerCase() === CONTRACT,
  revEvent ? `合约=${revEvent.contract}，期望 ${CONTRACT}` : '（无事件）')

// --- 判据③：四个入口 ------------------------------------------------------
title('5.1 ★ 判据③：四个业务入口都要报 KEY_REVOKED')

// ① 取信封（node-self 约定：HTTP 恒 200，错误码在 body.data.error_code）
const ep1 = await api(PQKDS, '/node-self/envelopes/', { token: nodeB.token })
check('① GET /node-self/envelopes/：HTTP 200 但 code=409 且 error_code=KEY_REVOKED',
  ep1.status === 200 && ep1.body?.code === 409 && ep1.body?.data?.error_code === 'KEY_REVOKED',
  `HTTP=${ep1.status} code=${ep1.body?.code} ${errCodeOf(ep1.body)} msg=${ep1.body?.msg}`)

// ② 向 B 分发（这一层用真 HTTP 状态码；但**节点腿失败不改变整体 200** ——
//    它是"部分成功"，失败原因逐节点列在 data.failed[] 里）
//
// ⚠️ 这一批里 A 是好的、B 是坏的 —— 所以它同时是"部分成功"与"① 失败腿"的
//    证据。`succeeded_node_ids` 里没有 B，会话就不该为 B 建。
const pairRowsBeforeEp2 = pairPoolRows(nodeA.nodeId, nodeB.nodeId)
const ep2 = await api(PQKDS, '/key-pool/distribute-to-user/', {
  method: 'POST',
  token: nodeA.token,
  body: { source_key_id: Number(sourceKeyId), node_ids: [Number(nodeBId)], count: 1, node_wrapping_algorithm: 'kyber_kem' }
})
const ep2Failed = ep2.body?.data?.failed || []
const ep2BRow = (ep2.body?.data?.nodeResults || []).find((r) => r.nodeCode === nodeB.nodeId)
check('② distribute-to-user：B 这一腿在 failed 里指名 KEY_REVOKED（不是一句"封装失败"）',
  isOk(ep2.body) && ep2Failed.some((line) => String(line).includes('KEY_REVOKED')),
  `failed=${JSON.stringify(ep2Failed)}`)
check('② 整体状态是 partial，且 B 的 nodeResults 行 delivered=false',
  ep2.body?.data?.status === 'partial' && ep2BRow?.delivered === false,
  `status=${ep2.body?.data?.status} B行=${JSON.stringify(ep2BRow)}`)

// ⚠️ 复核点名的第二处退化：旧版直接写 `LIKE '${batchId || ''}-%'` —— batchId
//    缺失时模式退化成 `LIKE '-%'`，几乎必空，"没有会话"白送。
//    补法是**先断言 batchId 存在**，再按它查；这样 batchId 缺失会先在这里红。
const ep2BatchId = ep2.body?.data?.batchId || ''
check('★ ② 被拒的这一批也回传了 batchId（下面按它查会话/池行，缺了断言就退化成 LIKE \'-%\'）',
  Boolean(ep2BatchId), `batchId=${JSON.stringify(ep2.body?.data?.batchId)}`)
check('② 被拒的节点**没有**因此多出一条会话（失败腿不建会话）',
  Boolean(ep2BatchId)
  && !sqlScalar(`SELECT session_id FROM ${SESSION_TABLE} WHERE session_id LIKE '${ep2BatchId}-%' LIMIT 1;`),
  `batchId=${ep2BatchId} 会话=${sqlScalar(`SELECT IFNULL(GROUP_CONCAT(session_id), '') FROM ${SESSION_TABLE} WHERE session_id LIKE '${ep2BatchId}-%';`)}`)

// ⚠️ 复核点名的第三处：失败腿在封装**之前** `continue`，结构上不会落池行，
//    但旧脚本没有为它写过任何断言。补一条**独立**证据：这一批在池表里
//    最多只该有 A 那一腿的行，绝不该有 B 的。
check('★ ② 失败腿没有落下任何属于 B 的池行（failed[] 里那句话之外，库里也要干净）',
  Boolean(ep2BatchId) && Number(sqlScalar(
    `SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='${ep2BatchId}' AND node1_id=${ownerId(nodeB.nodeId)};`
  ) || 0) === 0,
  `batchId=${ep2BatchId} 属于 B 的池行=${sqlScalar(`SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='${ep2BatchId}' AND node1_id=${ownerId(nodeB.nodeId)};`)}`)

// ③ 预分配（key-pool 约定：HTTP 恒 200、code=400、错误码**没有字段**、只在 msg 文本里）
const ep3 = await api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId, algorithm: 'kyber_kem', count: 1 }
})
check('③ /key-pool/generate/：code=400，且 msg 里指名 KEY_REVOKED（这个命名空间没有错误码字段）',
  ep3.status === 200 && ep3.body?.code === 400 && String(ep3.body?.msg || '').includes('KEY_REVOKED'),
  `HTTP=${ep3.status} code=${ep3.body?.code} msg=${ep3.body?.msg}`)

// ⚠️ 复核点名的第四处（原版是整条脚本里最空洞的一条）。旧写法：
//      `poolCounts(ep3.data.pool_id || 'no-such-pool').total === 0
//       || ep3.data.pool_id === undefined`
//    被拒响应本来就不带 pool_id，两个析取支同时平凡为真 —— 生成端就算在别处
//    落了半池（pool_id 没回显），断言照样绿。
//    换成**全局**的节点对计数差：不管 pool_id 是哪个、是否回显，只要这一对
//    多出一行就红。
const pairRowsAfterEp3 = pairPoolRows(nodeA.nodeId, nodeB.nodeId)
check('★ ③ 被拒之后该节点对（A,B）的全局池行数**一条都没多**（不是看响应回没回 pool_id）',
  pairRowsAfterEp3 === pairRowsBeforeEp2,
  `被拒前 ${pairRowsBeforeEp2} 行 → 被拒后 ${pairRowsAfterEp3} 行`
  + `（响应里 pool_id=${JSON.stringify(ep3.body?.data?.pool_id)} —— 有没有它都不影响这条断言）`)

// ④ 线上预分配（闸门在**发送方**：这一支撤的是 B 的密钥，所以让 B 当 sender）
const ep4 = await api(PQKDS, '/key-pool/distribute/', {
  method: 'POST',
  body: { sender_node_id: nodeB.nodeId, receiver_node_id: nodeA.nodeId, count: 1 }
})
check('④ /key-pool/distribute/：闸门在发送方，code=400 且 msg 里指名 KEY_REVOKED',
  ep4.status === 200 && ep4.body?.code === 400 && String(ep4.body?.msg || '').includes('KEY_REVOKED'),
  `HTTP=${ep4.status} code=${ep4.body?.code} msg=${ep4.body?.msg}`)

// ---------------------------------------------------------------------------
// 6. FALCON 签名闸门：另一条调用点，另一套响应约定
// ---------------------------------------------------------------------------
title('6. ★ 回收 A 的 FALCON：签名闸门要报 KEY_REVOKED（真 HTTP 409）')
info('分发在给信封签名**之前**先判发送方的 FALCON 是否可用。这条闸门有个前置条件：')
info('只在 `falcon_sign_private_key` 这一列非空时才判（从未生成过签名密钥的节点，')
info('既有行为是"不签名、分发照常"）。')
info('§3.6 已经把一把**真** Falcon-512 私钥种进这一列，并证明放行分支会真签名 ——')
info('所以本节这次拒绝**不是**"列里塞了读不懂的垃圾所以签不出来"，')
info('而是登记表明说这把密钥已回收。两者的区别恰恰是本节要证明的东西。')

check('★ 前置条件成立：§3.6 种下的私钥此刻仍在列里（否则本节测的不是回收那条分支）',
  (sqlScalar(`SELECT IFNULL(falcon_sign_private_key, '') FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || '') !== '',
  `falcon_sign_private_key 长度=${(sqlScalar(`SELECT LENGTH(IFNULL(falcon_sign_private_key, '')) FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || '0')}`)

const revA = await revoke(nodeA, FALCON, keys.A[FALCON].keyId, keys.A[FALCON].version,
  'KMS-007 验收：回收后签名闸门要报 KEY_REVOKED')
check('回收 A 的 FALCON 成功', revA.status === 200 && isOk(revA.body),
  `code=${revA.body?.code} msg=${revA.body?.msg}`)
check('★ 回收**没有**清掉私钥列 —— 它不再是判定依据，清掉反而毁掉取证线索',
  (sqlScalar(`SELECT IFNULL(falcon_sign_private_key, '') FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || '') !== '',
  '私钥列原样保留（与 §4.2「不做的」一致）')
check('★ 影响面：这次撤的是 A 的密钥，而三个池子记的都是 B 的引用 —— 精确面与退化面都不该命中',
  revA.body?.data?.impact?.poolItems === 0,
  `poolItems=${revA.body?.data?.impact?.poolItems}（撤别人引用的密钥不得误伤池项）`)
check('★ 影响面：上一次回收已把那条会话撤掉，这次不该再有会话被扫到',
  revA.body?.data?.impact?.sessions === 0 && revA.body?.data?.impact?.sessionsOk === true,
  `sessions=${revA.body?.data?.impact?.sessions} ok=${revA.body?.data?.impact?.sessionsOk}`)
check('三个池子都原封不动',
  poolCounts(poolK2v2).revoked === k2v2Ready
  && poolCounts(poolK2v1).ready === k2v1Ready
  && poolCounts(poolK1).ready === k1Ready)

const ep5 = await api(PQKDS, '/key-pool/distribute-to-user/', {
  method: 'POST',
  token: nodeA.token,
  body: { source_key_id: Number(sourceKeyId), node_ids: [Number(nodeBId)], count: 1, node_wrapping_algorithm: 'kyber_kem' }
})
check('★ ⑤ 签名闸门：整批被拒，HTTP 409（这一层用真状态码，不是恒 200）',
  ep5.status === 409,
  `HTTP=${ep5.status} code=${ep5.body?.code} message=${ep5.body?.message}`)
check('★ ⑤ 拒绝理由是 KEY_REVOKED（在 message 文本里，这一层没有 error_code 字段）',
  String(ep5.body?.message || '').startsWith('KEY_REVOKED：'),
  `message=${JSON.stringify(ep5.body?.message)}`)

// ---------------------------------------------------------------------------
// 7. ★ 正对照：回收 B 的 K1/v1（另一个 keyId，且已不在产），poolK1 这时**才**该灭
// ---------------------------------------------------------------------------
title('7. ★ 正对照：回收 B 的 K1/v1 → poolK1 这时才该失效')
info('这条同时证明三件事：① 第 5 节的"还活着"不是因为池项根本不会被回收；')
info('② 撤一把**非在产**的版本照样会精确清掉它名下的池项（wasActive=false）；')
info('③ 命中范围与第 5 节互补 —— 那次命中 K2/v2，这次命中 K1/v1，互不越界。')

const revK1 = await revoke(nodeB, KYBER, K1.keyId, K1.version, 'KMS-007 验收：池项正对照（回收另一个 keyId）')
check('回收 K1/v1 成功（它是 RETIRED，不是生产版本）',
  revK1.status === 200 && isOk(revK1.body), `code=${revK1.body?.code} msg=${revK1.body?.msg}`)
check('★ 撤的不是生产版本：wasActive=false（不必对"撤到了在产版"报成功）',
  revK1.body?.data?.revoked?.wasActive === false,
  JSON.stringify(revK1.body?.data?.revoked))
const k1Final = poolCounts(poolK1)
check('★ poolK1 的池项全部转入 REVOKED，且影响面数与库内一致',
  revK1.body?.data?.impact?.poolItems === k1Ready
  && k1Final.revoked === k1Ready && k1Final.ready === 0,
  `响应 ${revK1.body?.data?.impact?.poolItems}，库里 ${JSON.stringify(k1Final)}`)
check('poolK2v1 不受影响（它引用的是 K2/v1，与这次撤的 keyId 不同）',
  poolCounts(poolK2v1).ready === k2v1Ready)
check('poolK2v2 也不受影响（它早就是 REVOKED 了，不该被二次改动）',
  poolCounts(poolK2v2).revoked === k2v2Ready)

// ---------------------------------------------------------------------------
// 8. ★ 重试语义：重复回收是明确的终态，影响面不再变化
// ---------------------------------------------------------------------------
title('8. ★ 幂等：重复回收同一把')
const invBefore = invalidationCount(preSession)
const retry = await revoke(nodeB, KYBER, K2v2.keyId, K2v2.version, 'KMS-007 验收：重复回收')
const retryData = retry.body?.data || {}
check('重试仍然成功（是"已是终态"的明确回答，不是报错）',
  retry.status === 200 && isOk(retry.body), `code=${retry.body?.code} msg=${retry.body?.msg}`)
check('★ alreadyRevoked=true —— "这次撤的"与"早就撤了"必须可区分',
  retryData.revoked?.alreadyRevoked === true && retryData.revoked?.wasActive === false,
  JSON.stringify(retryData.revoked))
const eventsBeforeRetry = revokedEventsFor(eventsAfterRevoke, k2v2RowId, nodeB.nodeId)
check('★ 重试**不重复上链**：chainHash 是空串（同一次回收在链上留多条，"回收了几次"就没答案了）',
  String(retryData.chainHash || '') === '',
  `chainHash=${JSON.stringify(retryData.chainHash)}`)
// ⚠️ `chainHash === ''` 只是响应自证：字段缺失与"确实没上链"同形。
//    下面这条数**链上**该 keyId 的 KEY_REVOKED 事件条数 —— 它不经过被测服务端。
const eventsAfterRetry = revokedEventsFor(await scanLifecycleEvents(), k2v2RowId, nodeB.nodeId)
check('★★ 链上该 keyId 的 KEY_REVOKED 事件**仍然只有 1 条**（重试没有新增，独立于响应）',
  eventsAfterRetry.length === 1 && eventsBeforeRetry.length === 1,
  `重试前 ${eventsBeforeRetry.length} 条 → 重试后 ${eventsAfterRetry.length} 条`
  + `（tx=${eventsAfterRetry.map((e) => e.txHash.slice(0, 18)).join(',')}）`)
check('★ 影响面不再变化：池项 0、会话 0、会话处理成功',
  retryData.impact?.poolItems === 0 && retryData.impact?.sessions === 0
  && retryData.impact?.sessionsOk === true,
  JSON.stringify(retryData.impact))
check('★ 重试没有新写一条会话失效记录（那会让"失效了几次"失真）',
  invalidationCount(preSession) === invBefore,
  `${invBefore} → ${invalidationCount(preSession)}`)
// 哨兵在整条脚本的**最后**再查一次：从 §3.7 建好到现在，一共发生过 3 次回收、
// 2 次分发、1 次重试 —— 任何一次把"按节点匹配"写成"扫全表"，它都会翻成 revoked。
check('★★ 反例哨兵终检：全程 3 次回收之后仍为 initiated，且没有失效记录',
  sessionStatus(sentinelSession) === 'initiated' && invalidationCount(sentinelSession) === 0,
  `哨兵=${sessionStatus(sentinelSession)} 失效记录=${invalidationCount(sentinelSession)}`)

// ---------------------------------------------------------------------------
// 9. 清理：脚本自建自清
// ---------------------------------------------------------------------------
title('9. 清理：删掉本脚本建的节点及其一切关联行')
info('KMS-005/006 的旧脚本不清理，开发库的节点数一直在涨 —— 这一节就是为了不再涨。')
info('按 **domain_id** 捞而不是按记下来的两个 id：`newNodeSession` 在"建好节点、')
info('还没激活"之间抛出时，脚本根本不知道那个 id 存在；按域捞能把这种孤儿一起清掉。')

/**
 * 清理必须走 Django ORM，不能直接 SQL DELETE。
 *
 * 三个理由，都会让"看起来删掉了"其实没删干净：
 *   * 池项、会话、会话失效记录、长期密钥、节点鉴权的外键都是 `on_delete=CASCADE`，
 *     但那是 **Django 层**的行为 —— 库里并没有 `ON DELETE CASCADE`，
 *     裸 SQL DELETE 会直接撞外键约束报错；
 *   * `UserKeyEnvelope` 与 `DistributionBatch` 的 `user_id` 是**逻辑引用**
 *     （BigIntegerField，没有外键）—— 它们不在任何级联里，必须显式删；
 *   * 删不干净不会报错，只会让下一次跑时的夹具撞上历史数据（例如
 *     "这个节点已经有会话了"），而失败看起来像被测代码错了。
 *
 * 多行程序走 **stdin**（`python -`）而不是 `-c`：Windows 的 argv 处理会
 * 把多行字符串拆坏，而错误信息只会说"语法错误"。`MSYS_NO_PATHCONV=1`
 * 是因为 `/backend` 会被 Git Bash 改写成 `C:/Program Files/...`。
 */
const cleanupProgram = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node, UserKeyEnvelope, DistributionBatch

nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
user_ids = [n.sys_user_id for n in nodes if n.sys_user_id]
envelopes, _ = UserKeyEnvelope.objects.filter(user_id__in=user_ids).delete()
batches, _ = DistributionBatch.objects.filter(user_id__in=user_ids).delete()
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d(%s) user_key_envelopes=%d distribution_batches=%d cascaded=%d left=%d'
      % (len(ids), ','.join(str(i) for i in ids), envelopes, batches, deleted, left))
`

let cleanupOut = ''
let cleanupErr = ''
try {
  cleanupOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
    input: cleanupProgram,
    encoding: 'utf8',
    env: { ...process.env, MSYS_NO_PATHCONV: '1' }
  }).trim()
} catch (error) {
  cleanupErr = String(error?.stderr || error?.message || error)
}
info(cleanupOut || cleanupErr)
check('清理完成：域内不再有本脚本建的节点',
  Boolean(cleanupOut) && cleanupOut.endsWith('left=0'),
  cleanupOut || cleanupErr)

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId} / 哨兵 ${nodeC.nodeId} / ${nodeD.nodeId}（已在上面删掉）`)
info('证据都在上面：长期密钥表的终态与回收原因（B 的 K2/v2、K1/v1 与 A 的 FALCON）、物化列、')
info('池项三个池子的状态分布（目标池全灭、另有 keyId 与老版本两个池子原封不动）、')
info('会话行与失效记录、无关节点对哨兵全程 active、四个入口各自的错误形态，')
info('以及**从链上读回**的 KEY_REVOKED 事件（eventType/keyId/版本/节点/摘要逐字段比对，')
info('重试后条数仍为 1）。')
finish()
