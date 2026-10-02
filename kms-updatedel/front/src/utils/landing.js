/**
 * 登录后落地页（按登录主体分叉）。
 *
 * 为什么单独一个模块
 * ----------------
 * 「根路径该落到哪一页」这个判断要在三处一致：路由守卫、顶栏退出登录后的
 * 回跳、以及将来任何按角色给默认页的地方。散着写必然漂移 —— 仓库里
 * `role_level` 的判据曾因三处各写一份而分裂过（见 utils/principal.js 的注释）。
 *
 * 两棵菜单树（见 doc/admin-node-login-design.md §11）
 * -------------------------------------------------
 *   管理端 §9/§11.1  → 系统总览 `/index`
 *   节点端 §10/§11.2 → 工作台   `/workbench`
 *
 * ⚠️ 这里只决定**根路径**的落地页，不构成准入。
 *    某个页面能不能进，由 sys_menu 下发的菜单决定（见 store/modules/permission.js）；
 *    `permission.js` 守卫里的 isAdminLevel 只负责把"既不是管理员也不是节点"的
 *    账号挡在管理端之外。两者别混。
 */

import { PRINCIPAL_NODE, resolvePrincipalType } from '@/utils/principal'

/** 管理端的落地页（静态路由，见 router/index.js） */
export const ADMIN_LANDING = '/index'

/**
 * 节点端的落地页 = **工作台**（sys_menu 9050，由后端下发）。
 *
 * 工作台同时承担两件事（2026-09-30 合为一体）：
 *   * 顶部是三个业务子系统的入口卡片（**主元素**）——"接下来去哪"
 *   * 下面是与本节点相关的统计图表 ——"现在是什么状态"
 * 登录后直接落在它上面，不再经过一个单独的门户页：
 * 门户与总览本是同一件事的两面，拆成两页要多点一次才能看到状态。
 *
 * ⚠️ 它是**动态菜单页**，理论上可能因未授权而不存在。真出现那种情况，
 *    守卫会落到 `/` 再被改投一次，不会白屏。
 */
export const NODE_LANDING = '/workbench'

/** 当前主体应落到哪一页 */
export function landingPath(src = {}) {
  return resolvePrincipalType(src) === PRINCIPAL_NODE ? NODE_LANDING : ADMIN_LANDING
}

/**
 * 该路径是不是**管理端专属**的落地页。
 *
 * 只认 `/index`：`/` 会被 router 的 redirect 解析成 `/index` 后再进守卫，
 * 所以守卫里看不到 `/`，不必单独列出（列了是死条件，会误导读者）。
 *
 * 刻意**不**把整个管理端分区（/console、/reggov…）列进来：节点即使手敲这些
 * URL，菜单里没有它们、页面调的管理端接口也会被后端按权限拒掉；
 * 在前端做全量拦截等于把授权逻辑复制一份，两份必然漂移。
 */
export function isAdminLanding(path) {
  return path === ADMIN_LANDING
}

/**
 * 只在**节点端**出现的菜单路径（`sys_menu.path`，不含前导斜杠的叶子段）。
 *
 * 为什么需要这个：`admin` 账号在 RuoYi 里是**超级管理员**（user_id=1），
 * 后端 `selectMenuTreeByUserId` 对它**跳过 sys_role_menu 过滤**，直接返回
 * **全部**启用菜单。所以 41_*.sql 里"role 1 只授管理端、role 2 只授节点端"
 * 这套授权分叉，对 admin 这个账号不生效 —— 它会同时看到两棵树。
 *
 * ⚠️ 判据用 **path** 而不是 menu_id：`RouterVo` 里根本没有 menuId 字段
 *    （只有 name/path/hidden/redirect/component/query/alwaysShow/meta/children），
 *    主键传不到前端。而 path 的**全局唯一**正是迁移脚本里的硬约束
 *    （后端路由名 = capitalize(path)，vue-router 重名会顶掉旧路由），
 *    所以拿它当判据是可靠的。
 */
export const NODE_ONLY_FRAME_PATHS = Object.freeze(['workbench'])

/** 节点端的三个业务分区 + 节点信息分区（顶层目录的 path） */
export const NODE_ONLY_ZONE_PATHS = Object.freeze(['/genzone', '/lifezone', '/distzone', '/selfzone'])

/**
 * 管理端的顶层路径 —— 节点端侧边栏**不该出现**这些。
 *
 * 为什么需要：侧边栏是 `constantRoutes.concat(动态菜单)`。`constantRoutes` 里
 * 有管理端的静态页（仪表盘 `/index`、个人中心、重定向、404…），它对**所有**
 * 主体都一样下发。节点拿到的动态菜单虽然只有节点端那棵，
 * 但静态那份会跟着一起进侧边栏。
 *
 * 实测（2026-09-30，闭环测试）：节点登录后侧边栏第一条是「总览仪表盘」——
 * 那是管理端的页面，节点点进去也拿不到数据。这正是"进去了却是个公共侧边栏"
 * 那类问题的残余。
 *
 * ⚠️ 只排 `/index` 这一个。
 *    个人中心 `/user/profile`、`/redirect`、`/401`、`/404` 不是侧边栏条目
 *    （hidden:true），排不排都一样；而 `/index` 是唯一会被渲染出来的。
 *    不要顺手把整个管理端分区也列进来 —— 那些是动态菜单，节点根本拿不到，
 *    列了是死条件，只会让人误以为这里在做权限控制。
 */
export const ADMIN_ONLY_TOP_PATHS = Object.freeze(['/index'])

/**
 * 按登录主体过滤侧边栏。
 *
 * ⚠️ 这是一层**视图收敛**，不是权限边界。
 *    真正拦住请求的是后端按 `sys_role_menu` 下发的菜单与各接口自己的校验 ——
 *    节点手敲管理端 URL 时，页面调的管理端接口会被后端拒掉。
 *    前端这层只解决"界面不该同时摆两套入口"，不要把它当成授权。
 *
 * @param {Array} routes     permissionStore.sidebarRouters
 * @param {number|string|null} roleLevel
 * @param {'ADMIN'|'NODE'} [principal]  登录主体；不给则只按角色裁剪
 */
export function filterSidebarByPrincipal(routes, roleLevel, principal) {
  if (!Array.isArray(routes)) return []

  // 节点端：摘掉管理端的静态页（仪表盘等）。
  // `constantRoutes` 对所有主体一视同仁地下发，节点只筛动态菜单是筛不掉的 ——
  // 实测节点登录后第一条就是「总览仪表盘」。
  //
  // ⚠️ 仪表盘在 `constantRoutes` 里不是顶层条目，而是一个 **`path: ''` 的框架**
  //    加一个 `path: '/index'` 的子项（见 router/index.js 的 `redirect: '/index'`）。
  //    所以必须**进到 children 里**按子项 path 匹配 —— 只看顶层 `route.path`
  //    永远匹配不上，过滤会"跑过了但没效果"（2026-09-30 实测踩到）。
  if (principal === 'NODE') {
    const adminOnly = new Set(ADMIN_ONLY_TOP_PATHS)
    return routes
      .filter((route) => !adminOnly.has(route.path))
      .map((route) => {
        if (route.path !== '' || !Array.isArray(route.children)) return route
        const kept = route.children.filter((c) => !adminOnly.has(c.path))
        return kept.length === route.children.length ? route : { ...route, children: kept }
      })
      // 子项被摘空的框架（只剩一个空壳目录）也要去掉，
      // 否则侧边栏会留一个点开没内容的条目
      .filter((route) => !(route.path === '' && Array.isArray(route.children) && route.children.length === 0))
  }

  // 超管豁免的账号（role_level <= 0）拿到的是**全部**菜单，
  // 会同时看到管理端与节点端两棵树，这里把节点端那一棵摘掉。
  // 节点与普通管理员拿到的本来就是各自那一棵，不动。
  if (!(Number(roleLevel) <= 0)) return routes

  const zones = new Set(NODE_ONLY_ZONE_PATHS)
  const frames = new Set(NODE_ONLY_FRAME_PATHS)

  return routes.filter((route) => {
    // 1) 节点端的业务分区目录，直接整棵摘掉
    if (zones.has(route.path)) return false

    // 2) 顶层 C 类型的"单页框架"：它的 path 是 `/`，真正的页面在 children 里。
    //    只有在**所有**子项都是节点端页面时才摘 —— 管理端的「系统总览」
    //    「区块链存证」「操作日志」「验收测试台」同样是 `/` 框架，不能误伤。
    const children = route.children || []
    if (route.path === '/' && children.length) {
      const allNodeOnly = children.every((c) => frames.has(String(c.path || '').replace(/^\/+/, '')))
      if (allNodeOnly) return false
    }

    return true
  })
}
