/**
 * 角色判定（Q2 / D13：角色收成 2 级）。
 *
 * | role_level | 含义     |
 * |------------|----------|
 * | 0          | 管理员   |
 * | 2          | 普通用户 |
 *
 * 历史上存在 1 =「中级用户」，其**唯一**用途是放行 PUBLIC_KEY_LIST；
 * 该功能已按 D1 整体删除，等级 1 随之废弃。全部判定收敛到 `<= 0` 这一个判据，
 * 禁止再出现 `<= 1` 之类的比较（存量数据已确认无 level=1 账号）。
 */

/** 是否管理员 */
export function isAdminLevel(roleLevel) {
  return Number(roleLevel) <= 0
}

/** 角色中文名（只用于展示） */
export function roleLevelText(roleLevel) {
  return isAdminLevel(roleLevel) ? '管理员' : '普通用户'
}
