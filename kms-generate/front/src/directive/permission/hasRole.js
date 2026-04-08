import auth from '@/plugins/auth'

export default {
  mounted(el, binding, vnode) {
    const { value } = binding
    const all_permission = "*:*:*"
    const permissions = auth.hasPermiOr(value)
    if (!permissions) {
      el.parentNode && el.parentNode.removeChild(el)
    }
  }
}
