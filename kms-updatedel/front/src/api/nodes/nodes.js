import http, { unwrap, unwrapList } from '@/api/pqkds/http'

/**
 * 管理端「节点管理」接口。
 *
 * 数据住在分发模块（Django / falcon_kds）的 `falcon_kds.dvadmin_pqkds_nodes` 表，
 * 管理端只是它的调用方 —— 与「节点鉴权」页同一套路数，都走 `/pqkds-api/` 网关前缀。
 *
 * 为什么不再用 iframe 嵌 `/distribute/#/node`：
 * 那个子应用有自己的登录态，管理端里打开只会渲染出它的登录页（实测截图为证），
 * 于是"节点管理"这一项对已登录的管理员毫无用处。原生页面直接调这里的接口，
 * 复用管理端自己的登录态，不存在第二次登录。
 *
 * HTTP 客户端统一走 `@/api/pqkds/http`（同时认 200 与 2000 两种成功码），
 * 原因见那个文件顶部：分发模块两种信封并存，走 RuoYi 的 request 会把成功判成错误。
 *
 * 服务端权限现状（如实记录，不粉饰）：分发模块的 NodeViewSet 把
 * list/retrieve/create/update/destroy/batch_delete 全部放进了免鉴权白名单，
 * 也就是说这些接口不校验身份。管理端这一侧仍按登录态访问，但**不能**把
 * "页面上能看见"当成"服务端已授权"——真要收紧，得改分发模块。
 */

/** 节点列表 */
export function listNodes(params) {
  return http.get('/nodes/', { params: { page: 1, limit: 500, ...(params || {}) } }).then(unwrapList)
}

/**
 * 注册（新增）节点。
 *
 * 走 `register/` 而不是裸 POST `/nodes/`：前者会一并调用 node_service.register_node()
 * 为新节点生成**三套**密钥 —— Kyber、国密（SM2 + SSCL）、Falcon，
 * 这正是"演示节点开箱可用"的前提。后者只落一行记录。
 *
 * ⚠️ 耗时：整体约十几到二十秒（Falcon 占大头）。调用方必须显示 loading。
 */
export function registerNode(data) {
  return http.post('/nodes/register/', data).then(unwrap)
}

/** 更新节点。服务端只接受联系信息/类型/描述等字段，node_id/name/ip/port 是只读的 */
export function updateNode(id, data) {
  return http.patch(`/nodes/${id}/`, data).then(unwrap)
}

/** 删除单个节点 */
export function deleteNode(id) {
  return http.delete(`/nodes/${id}/`).then(unwrap)
}

/** 批量删除。服务端要求 `{ids: [...]}` */
export function batchDeleteNodes(ids) {
  return http.post('/nodes/batch_delete/', { ids }).then(unwrap)
}

/** 节点密钥概览（Kyber / Falcon 公钥是否就绪） */
export function getNodeKeys(id) {
  return http.get(`/nodes/${id}/keys/`).then(unwrap)
}

/**
 * 为节点生成 Falcon 密钥对（V2 陷门方案）。
 *
 * 为什么还需要它：**新建节点现在已经会自动生成 Falcon 密钥**（2026-09-26 起，
 * 见 pqkds/node_service.py 的 register_node），所以这个入口不再像以前那样是
 * "界面上唯一能补 Falcon 的途径"。但它仍然必要 —— 自动生成只记日志、不阻断注册，
 * 失败时那一行就停在"未生成"，必须有个地方能重试。
 *
 * 耗时参考（本机实测）：服务端 KGC 部分私钥 5.9s + 密钥对 1.9s，
 * 加上写库与上链，**一次约十几到二十秒**。调用方必须显示 loading、防重复点击，
 * 批量场景请串行执行（见 views/nodes/index.vue 的 handleBatchGenerateFalcon）。
 *
 * ⚠️ 对已有 Falcon 公钥的节点再次调用会**更换**密钥对，
 *    此前用旧公钥封装的密钥池将无法解开。调用方必须先向用户确认。
 *
 * @param {string} nodeId 节点编号（node_id，不是数据库主键 id）
 */
export function generateNodeFalconKey(nodeId) {
  return http
    .post('/node/generate-falcon-keypair/', { node_id: nodeId, scheme: 'v2' })
    .then(unwrap)
}

/**
 * 为节点生成**国密**密钥对（SM2 与 SSCL 各一对）。
 *
 * 用途：分发的节点腿算法由用户选（抗量子 Kyber/Falcon 或 国密 SM2/SSCL），
 * 选国密时要求节点已有对应国密公钥 —— 这个接口/按钮就是补这一步的入口。
 * 新建节点会自动带上国密密钥，所以这里主要用于给**历史节点**补生成。
 *
 * 与 Falcon 一样：对已有国密密钥的节点再次调用会**更换**密钥对，
 * 此前用它封装的密钥池将无法解开，调用方必须先确认。
 *
 * @param {string} nodeId 节点编号（node_id，不是数据库主键 id）
 */
export function generateNodeGmKey(nodeId) {
  return http.post('/node/generate-gm-keypair/', { node_id: nodeId }).then(unwrap)
}