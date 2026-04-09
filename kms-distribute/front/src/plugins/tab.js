import store from '@/store'

export default {
  // 刷新页面
  refresh() {
    store.dispatch('tagsView/delAllViews')
    const { fullPath } = this.$route
    this.$nextTick(() => {
      this.$router.replace({
        path: '/redirect' + fullPath
      })
    })
  },
  // 关闭当前页面
  close() {
    store.dispatch('tagsView/delView', this.$route)
    this.$router.go(-1)
  },
  // 关闭指定页面
  closeView(view) {
    return store.dispatch('tagsView/delView', view)
  },
  // 关闭所有页面
  closeAll() {
    return store.dispatch('tagsView/delAllViews')
  },
  // 关闭其他页面
  closeOthers(view) {
    return store.dispatch('tagsView/delOthersViews', view)
  },
  // 关闭左侧页面
  closeLeft(view) {
    return store.dispatch('tagsView/delLeftViews', view)
  },
  // 关闭右侧页面
  closeRight(view) {
    return store.dispatch('tagsView/delRightViews', view)
  }
}
