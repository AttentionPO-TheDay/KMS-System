import axios from 'axios'
import { getToken } from '@/utils/auth'

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

export const pqkdsBaseURL = import.meta.env.VITE_APP_PQKDS_API || '/pqkds-api'

/** 分发模块的两种成功码：手写视图 200，DRF ViewSet 2000 */
export const SUCCESS_CODES = [200, 2000]

const http = axios.create({ baseURL: pqkdsBaseURL, timeout: 60000 })

http.interceptors.request.use((config) => {
  // 带上管理端令牌：分发模块的多数接口现在不校验，但 /admin/* 会校验，
  // 带上不亏，将来收紧也不用改前端。
  const token = getToken()
  if (token) config.headers['Authorization'] = 'Bearer ' + token
  return config
})

http.interceptors.response.use(
  (res) => {
    const body = res.data
    // 非信封响应（例如裸数组）直接放行
    if (!body || typeof body !== 'object' || !('code' in body)) return body
    if (SUCCESS_CODES.includes(body.code)) return body
    const msg = body.msg || body.message || `分发模块返回 code=${body.code}`
    return Promise.reject(new Error(msg))
  },
  (error) => {
    const detail =
      error?.response?.data?.msg ||
      error?.response?.data?.message ||
      error?.response?.data?.detail ||
      error?.message ||
      '请求失败'
    return Promise.reject(new Error(detail))
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