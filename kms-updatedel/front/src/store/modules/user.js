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
        return new Promise((resolve, reject) => {
          login(username, password, code, uuid).then(res => {
            setToken(res.token)
            this.token = res.token
            resolve()
          }).catch(error => {
            reject(error)
          })
        })
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
        return new Promise((resolve, reject) => {
          logout(this.token).then(() => {
            this.token = ''
            this.roles = []
            this.permissions = []
            this.roleLevel = null
            this.principalType = null
            // 清节点初始化状态缓存：它按会话缓存，不清的话下一个登录的账号
            // 会继承上一个账号的主体/初始化状态（阶段 2）。
            resetNodeInitStatusCache()
            removeToken()
            resolve()
          }).catch(error => {
            reject(error)
          })
        })
      }
    }
  })

export default useUserStore
