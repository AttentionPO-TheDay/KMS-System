import http, { unwrap, unwrapList } from '@/api/pqkds/http'

/**
 * 管理端「节点鉴权」接口（P3 步骤 10）。
 *
 * 授权关系住在 `falcon_kds`，是分发模块自己的数据，管理端只是它的调用方，
 * 全部走 `/pqkds-api/` 网关前缀。
 *
 * ★ 这里以前用的是 `@/utils/request`，导致**取节点列表必然报错**：
 *   `/nodes/` 是 DRF ViewSet，成功时返回 `code: 2000`，而 RuoYi 的拦截器只认 200，
 *   于是把成功响应弹成错误通知并 `Promise.reject('error')` ——
 *   调用方写 `error.message` 得到 `undefined`，页面上就是
 *   "加载节点列表失败：undefined" + 一条内容其实是"获取节点列表成功…"的红色通知。
 *   现已统一改用 `@/api/pqkds/http`（认 200 与 2000）。
 *
 * 权限：`/admin/*` 这些接口会**授予他人访问节点的权限**，服务端要求
 * `roleLevel <= 0`（管理员）且校验 Bearer 令牌。前端不做判断，
 * 被拒时如实显示 403 的说明，而不是自己藏起按钮假装安全。
 */

/**
 * 节点列表（授权时要选节点）。走分发模块的 NodeViewSet：`/pqkds-api/nodes/`
 *
 * 顺带把字段名统一成驼峰：分发模块这个接口返回的是 `node_id`（下划线），
 * 而本页模板读 `n.nodeId`，于是下拉标签渲染成「演示节点2（undefined）」——
 * 接口 200、列表也有数据，只有编号位置是 undefined，很容易被当成"没取到"。
 * 授权列表接口（`/admin/*`）用的本来就是 `nodeName`/`nodeCode` 驼峰，
 * 这里补齐同样的键，页面上下两处口径就一致了。
 */
export function listDistributionNodes() {
  return http
    .get('/nodes/', { params: { page: 1, limit: 200 } })
    .then(unwrapList)
    .then((list) =>
      (list || []).map((n) => ({
        ...n,
        nodeId: n.node_id,
        nodeCode: n.node_id,
        nodeName: n.name
      }))
    )
}

/** 账号列表（用户选择器用；服务端代理转发，内部令牌不下发浏览器） */
export function listAdminUsers(keyword) {
  return http
    .get('/admin/users/', { params: keyword ? { keyword } : undefined })
    .then(unwrap)
}

/** 授权关系列表 */
export function listNodeAuthorizations(query) {
  return http.get('/admin/node-authorizations/', { params: query }).then(unwrap)
}

/** 授予某用户某节点的通信权限 */
export function grantNodeAuthorization(data) {
  return http.post('/admin/node-authorizations/', data).then(unwrap)
}

/** 撤销一条授权（服务端为软撤销，保留审计痕迹） */
export function revokeNodeAuthorization(id) {
  return http.post(`/admin/node-authorizations/${id}/revoke/`).then(unwrap)
}

// ---------------------------------------------------------------------------
// 节点授权申请（任务书「节点多级授权」）
// ---------------------------------------------------------------------------
// 节点在「节点授权」页发起申请，管理员在这里审批。
// ⚠️ 批准 = **真的写授权行**（默认双向各一行），不是改一个状态字 ——
//    放行判据自始至终只有 `UserNodeAuthorization` 一处。

/**
 * 授权申请列表。默认只看待审批（审批人先看要动手的）。
 *
 * 每行带 `existingForward` / `existingBackward`（这对节点已有的授权行，含已撤销的）
 * 与 `requesterUserMissing` / `targetUserMissing`（批准必然失败的前置条件）——
 * 前者决定批准时会"新建"还是"重新激活"，后者让界面先把按钮禁掉而不是等报错。
 */
export function listAuthorizationRequests(params) {
  return http.get('/admin/node-authorization-requests/', { params }).then(unwrap)
}

/**
 * 批准 / 驳回一条授权申请。
 *
 * @param {number} id 申请单主键
 * @param {{decision: 'approve'|'reject', remark?: string, bidirectional?: boolean}} payload
 *   `bidirectional` 缺省 true（申请表达的是"两个节点互通"）；显式 false 才是单授。
 *   驳回时 `remark` **必填** —— 节点侧看到的只有这句话。
 *
 * 回执里 `granted.created` / `granted.reactivated` 如实地分开说"这次改变了什么"，
 * `chainHash` 为空表示存证未成功（同时带 `chainWarning`），两者不要混成一句成功。
 */
export function decideAuthorizationRequest(id, payload) {
  return http.post(`/admin/node-authorization-requests/${id}/decide/`, payload).then(unwrap)
}