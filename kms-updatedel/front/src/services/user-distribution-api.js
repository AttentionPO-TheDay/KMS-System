import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

/**
 * 用户侧分发接口（P3 / §5.1）。
 *
 * 走 `/pqkds-api/`（分发模块 Django），**不是**旧的 `/distribute-api/`。
 * 旧的那条链路（kms-distribute Java + `kms.key_distribute_record`）在 P5 收敛删除。
 *
 * 身份：这四个接口的 `user_id` **一律由服务端从令牌解析**（经主 KMS 自省），
 * 前端不需要也不应该传 `user_id` —— 传了也会被忽略，而且那正是越权的入口。
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
 * @param {{sourceKeyId: number|string, nodeIds: number[], count?: number,
 *          nodeWrappingAlgorithm?: 'kyber_kem'|'falcon_lattice'}} payload
 *   `sourceKeyId` 必须是 SM2 / SSCL 的密钥（D17 由服务端强制，前端过滤只是体验优化）；
 *   `nodeWrappingAlgorithm` 是**节点腿**的封装算法，由用户选择（2026-09-26 起支持 Falcon）。
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
      // 节点腿封装算法（抗量子 Kyber / Falcon），由用户选择
      node_wrapping_algorithm: nodeWrappingAlgorithm
    }
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