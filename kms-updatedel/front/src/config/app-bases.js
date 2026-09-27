/**
 * 应用间跳转地址（集中定义，禁止在页面里散写路径字符串）。
 *
 * 背景（D9）：系统只有一个登录入口（kms-user）。管理员登录后被送到本应用
 * （管理控制台）；普通用户若直接访问本应用，会被路由守卫整页跳回用户前台。
 * 两个应用同源、base 不同，且共用同一个 `Admin-Token` Cookie，故跳转无需二次登录。
 */
export const appBases = {
  userConsole: import.meta.env.VITE_APP_USER_CONSOLE || '/user/'
}

/** 用户前台完整 URL（同源整页跳转用） */
export function userConsoleUrl() {
  return `${window.location.origin}${appBases.userConsole}`
}

/**
 * 唯一登录入口的 URL（用户前台的登录页）。
 *
 * 管理端**不再**渲染自己的登录页：未登录时整页跳到这里（见 permission.js）。
 * 此前管理端保留了自己的 login.vue，于是系统里有两个登录页，且两者验证码策略
 * 还不一样 —— 与上面 D9 的约定相矛盾。路径同样集中在这里，避免散写字符串。
 */
export function userLoginUrl() {
  return `${window.location.origin}${appBases.userConsole}login`
}