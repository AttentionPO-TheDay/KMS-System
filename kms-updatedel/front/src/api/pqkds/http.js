import axios from 'axios'
import { getToken } from '@/utils/auth'
import { IS_DEMO } from '@/utils/entry-mode'
import { applyDemoRequest } from '@/utils/demo-context'

/**
 * 访问分发模块（Django / falcon_kds）的**共用** HTTP 客户端。
 *
 * ★ 为什么不能直接用 `@/utils/request`
 * ------------------------------------
 * RuoYi 那个实例的响应拦截器按自家约定要求 `code === 200`，否则：
 *   1. 弹一条 `ElNotification.error({ title: 后端的 msg })`
 *   2. `Promise.reject('error')` —— 注意 reject 的是**字符串**，
 *      于是调用方写 `error.message` 只会得到 `undefined`。
 * 而分发模块里两种信封并存：
 *
 *   | 接口 | 返回 | 走 RuoYi request 的结果 |
 *   |---|---|---|
 *   | `/admin/users/`、`/admin/node-authorizations/`（手写视图） | `code: 200` | 正常 |
 *   | `/nodes/`、`/nodes/{id}/`（DRF ViewSet） | `code: 2000` | **成功也被判成错误** |
 *
 * 实际症状（2026-09-24 用户截图）：节点鉴权页左上角红条「加载节点列表失败：undefined」，
 * 右上角红通知「获取节点列表失败了…」，而后端那句话其实是
 * **"获取节点列表成功 - （未配置区块链，显示所有节点）(2个节点)"** —— 一个成功响应被当成错误播报。
 *
 * 所以这里单独建实例，成功码两种都认，且 reject 的是 `Error`（带 message），
 * 让调用方的 `error.message` 有意义。
 */

export const pqkdsBaseURL = IS_DEMO ? '/demo-api/pqkds' : (import.meta.env.VITE_APP_PQKDS_API || '/pqkds-api')

/** 分发模块的两种成功码：手写视图 200，DRF ViewSet 2000 */
export const SUCCESS_CODES = [200, 2000]

const http = axios.create({ baseURL: pqkdsBaseURL, timeout: 60000 })

/**
 * 造一个带业务码的错误再抛。
 *
 * 为什么不能只抛 message
 * ----------------------
 * 节点自助命名空间里**失败的种类是有意义的**：设备不一致
 * （`api_contract.ERR_DEVICE_MISMATCH`）是**可处置**的状态 —— 用户该做的是
 * "换回原设备"或"重新初始化"，与"参数写错了"要走的下一步完全不同。
 * 只留 message 的话，调用方就只剩"匹配文案"这一条路，而文案一改，
 * 分支会**静默**走错，不会有任何一处报错。
 *
 * 两个字段的分工（都在 Error 上，所以 `error.message` 的既有用法不受影响）：
 *   * `businessCode` —— 信封里的 `code`（200 / 409 / …），沿用各命名空间既有口径；
 *   * `errorCode`    —— 冻结契约里的 `api_contract.ERR_*`，可编程判断用。
 */
function fail(message, { businessCode, errorCode } = {}) {
  const error = new Error(message)
  if (businessCode !== undefined && businessCode !== null) error.businessCode = businessCode
  if (errorCode) error.errorCode = errorCode
  return error
}

http.interceptors.request.use((config) => {
  // 带上管理端令牌：分发模块的多数接口现在不校验，但 /admin/* 会校验，
  // 带上不亏，将来收紧也不用改前端。
  const token = getToken()
  if (token) config.headers['Authorization'] = 'Bearer ' + token
  if (IS_DEMO) applyDemoRequest(config, 'pqkds')
  return config
})

http.interceptors.response.use(
  (res) => {
    const body = res.data
    // 非信封响应（例如裸数组）直接放行
    if (!body || typeof body !== 'object' || !('code' in body)) return body
    if (SUCCESS_CODES.includes(body.code)) return body
    const msg = body.msg || body.message || `分发模块返回 code=${body.code}`
    // `data.error_code`：node-self 命名空间的失败体形状（见 `node_self_views._error`）
    return Promise.reject(fail(msg, { businessCode: body.code, errorCode: body.data?.error_code }))
  },
  (error) => {
    const body = error?.response?.data
    const detail =
      body?.msg ||
      body?.message ||
      body?.detail ||
      error?.message ||
      '请求失败'
    return Promise.reject(fail(detail, {
      // HTTP 状态码（真实状态的那套接口）与信封里的 code 都留着：
      // 前者是传输层的结论，后者是业务层的，两者都要能拿到才好判断。
      businessCode: body?.code ?? error?.response?.status,
      errorCode: body?.data?.error_code || body?.error_code
    }))
  }
)

/** 把信封拆开：`{code, msg, data}` → `data`；裸数据原样返回 */
export function unwrap(res) {
  return res && typeof res === 'object' && 'data' in res ? res.data : res
}

/**
 * 列表类响应归一成数组。分发模块这里又分三种形状：
 * 裸数组、`{data: [...]}`、DRF 分页 `{results: [...]}`。
 */
export function unwrapList(res) {
  const data = unwrap(res)
  if (Array.isArray(data)) return data
  return data?.results || data?.data || []
}

export default http