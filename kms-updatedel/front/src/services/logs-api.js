import { apiBases } from '@/config/api-bases'
import { requestJson } from '@/services/http'

/**
 * 「我的操作日志」数据源（Q8 / D14）。
 *
 * 三个接口都**不接收任何用户标识**：过滤条件由服务端从令牌推导
 * （见 kms-updatedel 的 `MyLogController`）。前端即使传 userId / userName
 * 也会被服务端覆盖，因此这里刻意不提供这类参数，避免误以为可以按他人查询。
 *
 * 日志源：
 *  - key-operations → `key_operation_record`（密钥更新/回收/接收，含链上信息）
 *  - operations     → `sys_oper_log`（RuoYi 记录的对本系统的接口调用）
 *  - logins         → `sys_logininfor`（登录成功与失败）
 */

function buildQuerySuffix(query = {}) {
  const search = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value).trim())
    }
  })
  return search.toString() ? `?${search.toString()}` : ''
}

export function listMyKeyOperations(query = {}) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/my-logs/key-operations${buildQuerySuffix(query)}`)
}

export function listMyOperations(query = {}) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/my-logs/operations${buildQuerySuffix(query)}`)
}

export function listMyLogins(query = {}) {
  return requestJson(apiBases.lifecycleApi, `/lifecycle/my-logs/logins${buildQuerySuffix(query)}`)
}
