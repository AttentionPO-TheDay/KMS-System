import { login, logout, getInfo } from '@/api/login'
import { getToken, setToken, removeToken } from '@/utils/auth'
import { isHttp, isEmpty } from "@/utils/validate"
import { resetNodeInitStatusCache } from '@/utils/node-init-status'
import defAva from '@/assets/images/profile.jpg'

const useUserStore = defineStore(
  'user',
  {
    state: () => ({
      token: getToken(),
      id: '',
      name: '',
      avatar: '',
      roles: [],
      permissions: [],
      roleLevel: null,  // 用户等级
      /**
       * 登录主体类型（阶段 2）：'ADMIN' | 'NODE' | null。
       *
       * 与 roleLevel 正交：principalType 决定「进哪个业务视图」，
       * roleLevel 是过渡期仍在生效的准入判据。两者的关系见 utils/principal.js。
       * 为 null 表示后端未返回（历史数据/接口未就绪）——按最小权限当 NODE 处理。
       */
      principalType: null
    }),
    actions: {
      // 登录
      login(userInfo) {
        const username = userInfo.username.trim()
        const password = userInfo.password
        const code = userInfo.code
        const uuid = userInfo.uuid
        return login(username, password, code, uuid).then(res => {
          const token = typeof res?.token === 'string' ? res.token.trim() : ''
          if (!token) {
            this.clearSession()
            throw new Error(res?.msg || '登录失败，服务器未返回有效令牌')
          }
          setToken(token)
          this.token = token
          return token
        }).catch(error => {
          // 登录失败时不能保留旧 token，否则路由守卫会把失败登录当成已登录会话。
          this.clearSession()
          throw error
        })
      },
      // 只清理浏览器本地会话，不请求后端。失效 token 场景下后端注销
      // 本身可能返回 401，路由恢复不能依赖那个请求成功。
      clearSession() {
        this.token = ''
        this.id = ''
        this.name = ''
        this.avatar = ''
        this.roles = []
        this.permissions = []
        this.roleLevel = null
        this.principalType = null
        resetNodeInitStatusCache()
        removeToken()
      },
      // 获取用户信息
      getInfo() {
        return new Promise((resolve, reject) => {
          getInfo().then(res => {
            const user = res.user
            let avatar = user.avatar || ""
            if (!isHttp(avatar)) {
              avatar = (isEmpty(avatar)) ? defAva : import.meta.env.VITE_APP_BASE_API + avatar
            }
            if (res.roles && res.roles.length > 0) { // 验证返回的roles是否是一个非空数组
              this.roles = res.roles
              this.permissions = res.permissions
            } else {
              this.roles = ['ROLE_DEFAULT']
            }
            this.id = user.userId
            this.name = user.userName
            this.avatar = avatar
            this.roleLevel = user.roleLevel  // 存储用户等级
            this.principalType = user.principalType  // 存储登录主体类型（ADMIN/NODE）
            resolve(res)
          }).catch(error => {
            reject(error)
          })
        })
      },
      // 退出系统
      logOut() {
        // 服务端注销是尽力而为；无论请求是否成功，都必须清掉本地会话，
        // 否则失效 token 会让后续路由继续被当成已登录状态。
        return logout(this.token)
          .catch(() => undefined)
          .then(() => this.clearSession())
      }
    }
  })

export default useUserStore
