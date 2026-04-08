import useUserStore from '@/store/modules/user'

/**
 * 是否有权限
 * @param {*} value
 */
export function hasPermi(value) {
  if (!value) {
    return true
  }
  const permissions = useUserStore().permissions
  if (permissions && permissions.length > 0) {
    return permissions.some(permission => {
      return permission === value || permission === '*:*:*'
    })
  }
  return false
}

/**
 * 是否有多个权限
 * @param {*} values
 */
export function hasPermiOr(values) {
  if (!values) {
    return true
  }
  const permissions = useUserStore().permissions
  if (permissions && permissions.length > 0) {
    return permissions.some(permission => {
      return values.includes(permission) || permission === '*:*:*'
    })
  }
  return false
}

/**
 * 是否包含所有权限
 * @param {*} values
 */
export function hasPermiAnd(values) {
  if (!values) {
    return true
  }
  const permissions = useUserStore().permissions
  if (permissions && permissions.length > 0) {
    return values.every(value => {
      return permissions.includes(value) || permissions.includes('*:*:*')
    })
  }
  return false
}

/**
 * 是否有角色
 * @param {*} value
 */
export function hasRole(value) {
  if (!value) {
    return true
  }
  const roles = useUserStore().roles
  if (roles && roles.length > 0) {
    return roles.some(role => {
      return role === value || role === '*'
    })
  }
  return false
}

/**
 * 是否有多个角色
 * @param {*} values
 */
export function hasRoleOr(values) {
  if (!values) {
    return true
  }
  const roles = useUserStore().roles
  if (roles && roles.length > 0) {
    return roles.some(role => {
      return values.includes(role) || role === '*'
    })
  }
  return false
}

/**
 * 是否包含所有角色
 * @param {*} values
 */
export function hasRoleAnd(values) {
  if (!values) {
    return true
  }
  const roles = useUserStore().roles
  if (roles && roles.length > 0) {
    return values.every(value => {
      return roles.includes(value) || roles.includes('*')
    })
  }
  return false
}

export default {
  hasPermi,
  hasPermiOr,
  hasPermiAnd,
  hasRole,
  hasRoleOr,
  hasRoleAnd
}
