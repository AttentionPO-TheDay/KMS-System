import auth from './auth'
import cache from './cache'
import modal from './modal'
import tab from './tab'
import download from './download'

export default {
  install(app) {
    // 权限方法
    app.config.globalProperties.$auth = auth
    // 缓存方法
    app.config.globalProperties.$cache = cache
    // 模态框方法
    app.config.globalProperties.$modal = modal
    // 页签方法
    app.config.globalProperties.$tab = tab
    // 下载方法
    app.config.globalProperties.$download = download
  }
}
