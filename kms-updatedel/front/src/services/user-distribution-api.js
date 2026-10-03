import { apiBases } from '@/config/api-bases'
import pqkdsHttp, { unwrap as unwrapPqkds } from '@/api/pqkds/http'
import { requestJson } from '@/services/http'

/**
 * 用户侧分发接口（P3 / §5.1）。
 *
 * 走 `/pqkds-api/`（分发模块 Django），**不是**旧的 `/distribute-api/`。
 * 旧的那条链路（kms-distribute Java + `kms.key_distribute_record`）在 P5 收敛删除。
 *
 * 身份：这些接口的 `user_id` **一律由服务端从令牌解析**（经主 KMS 自省），
 * 前端不需要也不应该传 `user_id` —— 传了也会被忽略，而且那正是越权的入口。
 *
 * ⚠️ 本模块里**两个 HTTP 客户端并存**，是刻意的（KMS-008 起）：
 *   * `requestJson`（RuoYi 实例）—— 旧接口用它，它的成功判据是 `code === 200`，
 *     失败时 `ElNotification` + `Promise.reject('error')`（**reject 字符串**，
 *     所以调用方拿不到 `error.errorCode`，只能提示文案）；
 *   * `@/api/pqkds/http`（`pqkdsHttp`）—— 新接口用它，它把 `data.error_code`
 *     提到 `error.errorCode` 上，页面才能**按错误码分支**（回收了 / 版本不对 /
 *     没授权，三种处置完全不同），而不是去匹配随时会改的文案。
 * 新写的接口一律用后者；旧接口保持原样，改动它们的错误面会波及既有页面。
 */

/**
 * 统一拆掉 `{code, message, data}` 信封，直接返回 `data`。
 *
 * 为什么需要它：本仓库的 `requestJson` 返回的是**响应体本身**。
 * 而不同后端的响应形状并不一致 —— RuoYi 系（generate/lifecycle）把列表直接放在
 * `rows`/`total` 上，而分发模块（Django）把载荷包在 `data` 里。
 * 如果页面按 `rows` 去取，就会静默拿到 `undefined`、表格空白、且**不报错** ——
 * 这类"页面空着但控制台干净"的问题最难查。所以在这里一次性对齐。
 */
function unwrap(response) {
  if (response && typeof response === 'object' && 'data' in response && 'code' in response) {
    return response.data
  }
  return response
}

/** 我被授权的节点（D5：只能往自己有权的节点发） */
export async function listUserNodes() {
  return unwrap(await requestJson(apiBases.pqkdsApi, '/user-nodes/'))
}

/**
 * 分发对称密钥给自己与选中的节点（D6）。
 *
 * ⚠️ **DEPRECATED（KMS-008）**：这是旧的**用户腿**模型 —— 必须先选一把
 * "我的解封密钥"（`sourceKeyId`），服务端为它再封一份"给自己解封"的信封。
 * 新模型是**节点到节点**，见下面的 `listPeerKeys` / `createNodeDistribution`。
 * 本函数保留一段迁移期（旧脚本与旧页面可能还在调），**新页面不得再使用**。
 *
 * @param {{sourceKeyId: number|string, nodeIds: number[], count?: number,
 *          nodeWrappingAlgorithm?: 'kyber_kem'|'gm_sm2'|'gm_sscl'}} payload
 *   `sourceKeyId` 必须是 SM2 / SSCL 的密钥（D17 由服务端强制，前端过滤只是体验优化）；
 *   `nodeWrappingAlgorithm` 是**节点腿**的封装算法。Falcon **不在**其中 ——
 *   它是签名算法，不提供机密性（计划 §3）。
 */
export async function distributeToUser({
  sourceKeyId,
  nodeIds,
  count = 1,
  nodeWrappingAlgorithm = 'kyber_kem'
}) {
  return unwrap(await requestJson(apiBases.pqkdsApi, '/key-pool/distribute-to-user/', {
    method: 'POST',
    body: {
      source_key_id: sourceKeyId,
      node_ids: nodeIds,
      count,
      // 节点腿封装算法（抗量子 Kyber 或国密两条），由用户选择
      node_wrapping_algorithm: nodeWrappingAlgorithm
    }
  }))
}

/**
 * 查**对端节点**可用于接收保护的长期密钥（KMS-008 / §16.1）。
 *
 * 页面上"接收方密钥版本"那一栏就是从这里来的：选定接收节点后拉一次，
 * 只列 `allowsNewWork === true` 的行让用户挑（**能不能用由服务端判**
 * —— `allowsNewWork` 取自 `api_contract`，前端不另写一套状态判断）。
 *
 * ⚠️ 路径里的是节点**业务编号**（`Node.node_id`），不是 `/user-nodes/` 回的
 *    那个 `nodeId`（那是主键）。传错的表现是"节点明明在，接口说它不存在"。
 *
 * @param {string} nodeCode 接收节点的业务编号
 * @param {string[]} [algorithms] 规范算法名（SM2/SSCL/KYBER）；不给则不过滤
 */
export async function listPeerKeys(nodeCode, algorithms) {
  const query = algorithms?.length ? `?algorithm=${encodeURIComponent(algorithms.join(','))}` : ''
  return unwrapPqkds(await pqkdsHttp.get(
    `/node-self/peers/${encodeURIComponent(nodeCode)}/keys/${query}`
  ))
}

/**
 * 发起一次**节点到节点**的分发（KMS-008 / §16.2 的新请求契约）。
 *
 * 与 `distributeToUser` 的差别（这就是"新契约"）：
 *   * **没有** `sourceKeyId` —— 不需要"我的解封密钥"；
 *   * 接收方密钥版本**显式指定**，服务端按**那一版**封装；
 *   * 只封给接收节点，没有"发起用户自己的那一份"。
 *
 * @param {{receiverNodeId: string, protectionAlgorithm: 'SM2'|'SSCL'|'KYBER',
 *          recipientKeyId: string, recipientKeyVersion: number, expiresInHours?: number}} payload
 *   `receiverNodeId` 是**业务编号**；`protectionAlgorithm` 用**规范名**
 *   （Falcon 会被服务端拒 —— 它是签名算法）。
 */
export async function createNodeDistribution({
  receiverNodeId,
  protectionAlgorithm,
  recipientKeyId,
  recipientKeyVersion,
  expiresInHours
}) {
  return unwrapPqkds(await pqkdsHttp.post('/node-self/distributions/', {
    receiverNodeId,
    protectionAlgorithm,
    recipientKeyId,
    recipientKeyVersion,
    ...(expiresInHours === undefined || expiresInHours === null || expiresInHours === ''
      ? {}
      : { expiresInHours })
  }))
}

/** 我的对称密钥列表（含剩余有效期） */
export async function listMySymmetricKeys(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return unwrap(await requestJson(apiBases.pqkdsApi, `/user-symmetric-keys/${suffix}`))
}

/** 单条对称密钥详情（含密文信封） */
export async function getMySymmetricKey(id) {
  return unwrap(await requestJson(apiBases.pqkdsApi, `/user-symmetric-keys/${id}/`))
}

/** 我的分发批次记录 */
export async function listDistributionBatches(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return unwrap(await requestJson(apiBases.pqkdsApi, `/distribution-batches/${suffix}`))
}