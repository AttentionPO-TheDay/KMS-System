/**
 * 登录主体类型（阶段 2）的判定与视图分流。
 *
 * 为什么单独一个模块
 * ----------------
 * 这套判据要在**四处**保持一致：路由守卫（permission.js）、顶栏、
 * 首次初始化引导页、以及各业务页的入口判断。散着写必然漂移 ——
 * 仓库里已经有过一次教训：`role_level` 的判据曾在三处各写一份，
 * 结果一处收紧、另两处没跟，出现"能进管理端但页面拒你"的分裂行为。
 *
 * 三个概念必须分清（文档 §2.2）
 * ---------------------------
 *   ① principalType   —— 登录主体是谁。ADMIN / NODE。**决定进哪个视图**。
 *   ② roleLevel       —— 过渡期的准入判据。前端 isAdminLevel() 读它。
 *   ③ permissionLevel —— 节点权限等级（L1/L2/L3），在 Node 表上，不在这里。
 *
 * 过渡期 ① 与 ② 必须一致，由迁移 31_*.sql 回填保证。本模块的
 * `resolvePrincipalType()` 守的正是这条不变量：当后端没返回 principalType
 * （历史数据、或接口未升级）时，**从 roleLevel 推导**，而不是默认放行。
 */

export const PRINCIPAL_ADMIN = 'ADMIN'
export const PRINCIPAL_NODE = 'NODE'

/**
 * 解析出当前账号的主体类型。
 *
 * 取值优先级：
 *   1. 后端明确返回的 principalType（大小写不敏感）
 *   2. 从 roleLevel 推导（roleLevel <= 0 → ADMIN，否则 NODE）
 *   3. 两者都没有 → NODE（**最小权限**）
 *
 * 第 3 条是刻意的：返回空值时若默认成 ADMIN，一个接口故障就会把所有
 * 用户放进管理端。宁可把管理员误判成节点（他能重新登录/由运维排查），
 * 也不能把节点误判成管理员。
 *
 * @param {{principalType?: string|null, roleLevel?: number|null}} src
 * @returns {'ADMIN'|'NODE'}
 */
export function resolvePrincipalType(src = {}) {
  const raw = (src.principalType || '').toString().trim().toUpperCase()
  if (raw === PRINCIPAL_ADMIN || raw === PRINCIPAL_NODE) {
    return raw
  }
  const level = src.roleLevel
  if (level === null || level === undefined || level === '') {
    return PRINCIPAL_NODE
  }
  return Number(level) <= 0 ? PRINCIPAL_ADMIN : PRINCIPAL_NODE
}

/** 是否平台管理员 */
export function isAdminPrincipal(src = {}) {
  return resolvePrincipalType(src) === PRINCIPAL_ADMIN
}

/** 是否区块链节点 */
export function isNodePrincipal(src = {}) {
  return resolvePrincipalType(src) === PRINCIPAL_NODE
}

/** 主体类型的中文展示名 */
export function principalTypeText(src = {}) {
  return isAdminPrincipal(src) ? '平台管理员' : '区块链节点'
}