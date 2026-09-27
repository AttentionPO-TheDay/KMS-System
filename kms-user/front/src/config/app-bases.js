/**
 * 应用间跳转地址（集中定义，禁止在页面里散写路径字符串）。
 *
 * 背景（D9）：系统只有一个登录入口（本应用），登录后按 `roleLevel` 分流——
 * 管理员进管理控制台，普通用户留在用户前台。管理控制台由 kms-updatedel
 * 这个**独立前端应用**承载，与用户前台同源但 base 不同，因此只能用
 * `window.location` 整页跳转，不能用 vue-router 跳转。
 *
 * 两个应用共用同一套后端与同一个 `Admin-Token` Cookie，所以跳转后无需再次登录。
 *
 * 管理端路径基线（P4 阶段由 /updatedel/ 改为 /admin/）只在这里改一处；
 * 同时必须同步 nginx `location`、vite `base` 与 .env，改后需重跑
 * `tools/smoke-frontends.mjs`（产物路径变化会影响缓存策略，见 kms-ops/README.md）。
 */
export const appBases = {
  adminConsole: import.meta.env.VITE_APP_ADMIN_CONSOLE || '/updatedel/'
}

/** 管理端完整 URL（同源整页跳转用） */
export function adminConsoleUrl() {
  return `${window.location.origin}${appBases.adminConsole}`
}