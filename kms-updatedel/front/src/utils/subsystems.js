/**
 * 节点端的三个业务子系统（文档 §11.2）。
 *
 * 一个子系统 = 侧边栏里的一棵子树 = `sys_menu` 里的一个顶层目录。
 * 分区靠 **menu_id** 认（后端已随 `/getRouters` 下发，见 `RouterVo.menuId` 的注释），
 * 不靠 `path` 或 `title` —— 那两个都会被迁移改名（41_*.sql 就改过多个），
 * 一旦改名靠字符串匹配的判断会**静默失效**。
 */

import { getNormalPath } from '@/utils/ruoyi'

/** sys_menu 里节点端四个顶层分区的 menu_id */
export const NODE_ZONE_MENU_IDS = Object.freeze({
  generate: 9400,      // 密钥生成 → 生成密钥 / 生成历史
  lifecycle: 9410,     // 更新与回收 → 我的密钥 / 密钥更新 / 版本历史 / 密钥回收
  distribution: 9420,  // 密钥分发 → 发起分发 / 预分配 / 密钥池 / 会话管理 / 分发记录
  self: 9430           // 节点信息 → 当前节点 / 本地密钥环境 / 我的日志
})

/** 三个**业务**子系统的 menu_id（「节点信息」不算业务子系统，见下方注释） */
export const BUSINESS_ZONE_MENU_IDS = Object.freeze([
  NODE_ZONE_MENU_IDS.generate,
  NODE_ZONE_MENU_IDS.lifecycle,
  NODE_ZONE_MENU_IDS.distribution
])

/** 工作台的 menu_id（顶层单页，不属于任何业务子系统） */
export const WORKBENCH_MENU_ID = 9050

/**
 * **不显示侧边栏**的菜单。
 *
 * 目前只有工作台：它是节点端刚进入时的主页面，整页都在做两件事 ——
 * 展示子系统入口与节点自己的数据。旁边再挂一列菜单会与页面内容争注意力，
 * 而且它本身不是"要在这里干活"的页面。
 *
 * 进任一业务子系统后侧边栏就会出现（只留该子系统那一棵），
 * 详见 layout/components/Sidebar/index.vue。
 *
 * ⚠️ 这条规则**只对节点端生效**（由 permission.js 按主体决定要不要打标），
 *    管理端不受影响 —— 管理员的落地页是 `/index`，其侧边栏照常。
 */
export const NO_SIDEBAR_MENU_IDS = Object.freeze([WORKBENCH_MENU_ID])

/**
 * 给匹配的菜单路由打上 `meta.hideSidebar`。
 *
 * 为什么必须在这一步做：`router.addRoute` 会**丢弃它不认识的顶层字段**
 * （只保留 name/path/components/meta/... ），所以 `menuId` 活不到组件里的
 * `route` 对象上 —— 组件的 `route` 里只有 `meta` 是可靠的。
 * 菜单刚解析出来时 `menuId` 还在，这里就地转成 meta 标记。
 */
export function applyNoSidebarMeta(routes) {
  if (!Array.isArray(routes)) return routes
  for (const route of routes) {
    if (NO_SIDEBAR_MENU_IDS.includes(Number(route.menuId))) {
      route.meta = { ...(route.meta || {}), hideSidebar: true }
    }
    if (Array.isArray(route.children)) {
      applyNoSidebarMeta(route.children)
    }
  }
  return routes
}

/**
 * 子系统门户上的三张卡片。
 *
 * ⚠️ 「节点信息」(9430) **不在门户上**：它不是业务子系统，而是
 *    "这个节点自己是谁"的说明页（§10.1/§10.2/§10.12）。做成卡片会让人
 *    以为它也是一条业务主线。它留在侧边栏里，从工作台能看到。
 *
 * ⚠️ 门户上**没有「工作台」卡片**：门户本身就是登录后的第一个页面，
 *    再放一张「工作台 → 进入」是绕圈子。工作台挂在侧边栏顶部，一点就到。
 */
export const SUBSYSTEMS = Object.freeze([
  Object.freeze({
    key: 'generate',
    title: '密钥生成',
    description: '创建新的长期密钥并查看生成结果',
    icon: 'Key',
    menuId: NODE_ZONE_MENU_IDS.generate
  }),
  Object.freeze({
    key: 'lifecycle',
    title: '密钥更新与回收',
    description: '管理密钥版本、轮换与终止',
    icon: 'Refresh',
    menuId: NODE_ZONE_MENU_IDS.lifecycle
  }),
  Object.freeze({
    key: 'distribution',
    title: '密钥分发',
    description: '建立短期会话并管理预分配密钥',
    icon: 'Share',
    menuId: NODE_ZONE_MENU_IDS.distribution
  })
])

/**
 * 从侧边栏路由里取出某个子系统那一棵。
 *
 * @returns {{zone: object, children: Array}|null}
 */
export function findSubsystemRoute(sidebarRouters, subsystem) {
  if (!Array.isArray(sidebarRouters) || !subsystem) return null
  const zone = sidebarRouters.find((r) => Number(r.menuId) === Number(subsystem.menuId))
  if (!zone) return null
  return { zone, children: Array.isArray(zone.children) ? zone.children : [] }
}

/** 把一条路由及其子树摊平成「绝对路径」集合，用于判断当前路由归属 */
function collectPaths(route, basePath = '') {
  if (!route || typeof route !== 'object') return []
  const own = getNormalPath(`${basePath}/${route.path || ''}`)
  const children = Array.isArray(route.children) ? route.children : []
  return [own, ...children.flatMap((c) => collectPaths(c, own))]
}

/** 当前路径是否落在某个顶层条目（含其子树）里 */
function routeContains(route, currentPath) {
  return collectPaths(route).includes(currentPath)
}

/**
 * 当前路由归属的**顶层分区条目**。不属于任何分区时返回 null。
 *
 * 用于"进入子系统后侧边栏只显示该子系统"——见 layout/components/Sidebar/index.vue。
 */
export function findOwningZone(sidebarRouters, currentPath) {
  if (!Array.isArray(sidebarRouters) || !currentPath) return null
  return sidebarRouters.find((r) => routeContains(r, currentPath)) || null
}

/** 该 menu_id 是不是三个业务子系统之一 */
export function isBusinessZone(menuId) {
  return BUSINESS_ZONE_MENU_IDS.includes(Number(menuId))
}

/**
 * 顶层单页（工作台这类）在菜单树里的真实落点。
 *
 * 为什么需要单独一个函数：顶层 `C` 类型（如工作台 9050）经 `buildMenus` 处理后，
 * 会变成一个 **`path: '/'` 的框架 + 一个子项**（`isMenuFrame` 分支），
 * 子项才带真实 path 与 menuId。所以"按 menuId 找页面"不能只看顶层 ——
 * 直接 `find(r => r.menuId === 9050)` 会返回 `null`，而那是**静默失败**：
 * 门户上那张卡会显示成"暂无权限"，用户以为没授权。
 *
 * @returns {string|null} 可直接 `router.push` 的绝对路径
 */
export function findTopLevelPagePath(sidebarRouters, menuId) {
  if (!Array.isArray(sidebarRouters)) return null
  // 情形一：框架的子项带 menuId（buildMenus 的 isMenuFrame 分支会把 menuId 设在子项上）
  for (const route of sidebarRouters) {
    for (const child of Array.isArray(route.children) ? route.children : []) {
      if (Number(child.menuId) === Number(menuId)) {
        const base = String(route.path || '').replace(/\/+$/, '')
        const childPath = String(child.path || '').replace(/^\/+/, '')
        return base ? `${base}/${childPath}` : `/${childPath}`
      }
    }
  }
  // 情形二：menuId 就在顶层条目上（普通目录/菜单）
  const direct = sidebarRouters.find((r) => Number(r.menuId) === Number(menuId))
  return direct ? String(direct.path) : null
}
