/**
 * 角色判定（Q2 / D13：角色收成 2 级）。
 *
 * | role_level | 含义     |
 * |------------|----------|
 * | 0          | 管理员   |
 * | 2          | 普通用户 |
 *
 * 管理端唯一的准入判据就是本函数。禁止再按 `role_id` 判定 —— `role_id` 是
 * RuoYi 的角色主键，与「是不是管理员」没有稳定对应关系（普通角色 id=2 被普通
 * 用户持有，而部分账号的 role_id 在 sys_role 中并不存在）。
 */

/** 是否管理员 */
export function isAdminLevel(roleLevel) {
  return Number(roleLevel) <= 0
}

/** 角色中文名（只用于展示） */
export function roleLevelText(roleLevel) {
  return isAdminLevel(roleLevel) ? '管理员' : '普通用户'
}
