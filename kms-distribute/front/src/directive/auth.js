import useUserStore from '@/store/modules/user'

/**
 * 权限指令
 * v-hasPermi="['system:user:add']"
 */
export default {
  mounted(el, binding, vnode) {
    const { value } = binding
    const all_permission = "*:*:*"
    const permissions = useUserStore().permissions

    if (value && value instanceof Array && value.length > 0) {
      const permissionFlag = value.some(permission => {
        return permissions.includes(permission) || all_permission.includes(permission)
      })

      if (!permissionFlag) {
        el.parentNode && el.parentNode.removeChild(el)
      }
    } else {
      throw new Error('请设置操作权限标签')
    }
  }
}
