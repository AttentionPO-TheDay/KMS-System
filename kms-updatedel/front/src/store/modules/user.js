import { login, logout, getInfo } from '@/api/login'
import { activateNode, getNodeChallenge, loginWithDevice } from '@/api/pqkds/node-self'
import { DEVICE_AUTH_ALGORITHM, ensureDeviceKey, signChallenge } from '@/utils/crypto/device-credential'
import { recordNodeLogin } from '@/utils/crypto/node-binding'
import { getToken, setToken, removeToken } from '@/utils/auth'
import { isHttp, isEmpty } from "@/utils/validate"
import { resetNodeInitStatusCache } from '@/utils/node-init-status'
import defAva from '@/assets/images/profile.jpg'
import { IS_DEMO } from '@/utils/entry-mode'
import { getDemoContext, logoutDemo } from '@/utils/demo-context'

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
      principalType: null,

      /**
       * 登录页**声明的**身份：'ADMIN' | 'NODE' | null（单一登录入口）。
       *
       * ⚠️ 这是"意图"，不是身份。真实身份永远是服务端 getInfo 返回的
       *    principalType/roleLevel。守卫会拿两者比对，不一致就清会话拒登 ——
       *    所以这个字段只用来提前拦下选错入口的人，**绝不能**当授权依据。
       *
       * 只存内存，不写 cookie/localStorage：刷新后应当由服务端身份说话。
       */
      declaredPrincipal: null
    }),
    actions: {
      // 登录
      login(userInfo) {
        const username = userInfo.username.trim()
        const password = userInfo.password
        const code = userInfo.code
        const uuid = userInfo.uuid
        this.declaredPrincipal = userInfo.declaredPrincipal || null
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
        this.declaredPrincipal = null
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
            // Demo authority, not URL or a standalone account, owns the role.
            this.principalType = IS_DEMO ? getDemoContext()?.principalType : user.principalType
            resolve(res)
          }).catch(error => {
            reject(error)
          })
        })
      },
      // 退出系统
      logOut() {
        if (IS_DEMO) return logoutDemo()
        // 服务端注销是尽力而为；无论请求是否成功，都必须清掉本地会话，
        // 否则失效 token 会让后续路由继续被当成已登录状态。
        return logout(this.token)
          .catch(() => undefined)
          .then(() => this.clearSession())
      },

      /**
       * 节点用**一次性激活凭证**完成首次激活（文档 §3）。
       *
       * 与 login() 的区别：这条路**没有口令**（节点账号的口令是随机且不披露的）。
       * 它做三件事，顺序不能反：
       *   1. 在本机生成设备认证密钥对（私钥不可导出，只留在本机）
       *   2. 把**公钥** + 激活凭证交给服务端，换回登录令牌
       *   3. 写下/刷新本机的**绑定文件**（`node-binding.js`）
       *
       * ⚠️ 第 1 步失败就不要走第 2 步 —— 否则凭证被消耗掉了、
       *    而本机没有对应的私钥，那个节点就再也不能用这台设备登录
       *    （只能找管理员重签凭证）。所以这里先确保密钥就绪再发请求。
       *
       * ⚠️ 第 3 步**不阻断**：令牌都已经发下来了，一次记账失败不该把
       *    已经成立的激活判成失败（`recordNodeLogin` 自己也不抛）。
       *
       * @param {{nodeId: string, code: string}} payload
       */
      activateNodeWithCode(payload) {
        const nodeId = String(payload?.nodeId || '').trim()
        const code = String(payload?.code || '').trim()
        if (!nodeId || !code) {
          return Promise.reject(new Error('请填写节点名称与激活凭证'))
        }
        this.declaredPrincipal = 'NODE'
        return ensureDeviceKey(nodeId)
          .then(({ publicKeyJwk }) => activateNode({
            nodeId,
            code,
            devicePublicKey: publicKeyJwk,
            deviceAlgorithm: DEVICE_AUTH_ALGORITHM,
          }))
          .then((res) => {
            const token = typeof res?.token === 'string' ? res.token.trim() : ''
            if (!token) {
              throw new Error('激活成功但服务器未返回有效令牌')
            }
            setToken(token)
            this.token = token
            return recordNodeLogin(nodeId, { name: res.name }).then(() => ({
              token, nodeId: res.nodeId, name: res.name,
            }))
          })
          .catch((error) => {
            // 激活失败同样不能留旧 token
            this.clearSession()
            throw error
          })
      },

      /**
       * 节点**免输入**登录：用本机设备私钥对服务端挑战签名（文档 §5）。
       *
       * 这就是"已激活节点列表里点一下就进去"背后的动作 ——
       * 用户不需要输入任何东西，因为证明身份的是**本机那把不可导出的私钥**。
       *
       * ⚠️ 登录成功后**立即刷新建档**：本机只保留"最后登录的那个节点"的
       *    绑定文件（首登时间保留，`loginCount` +1）。写失败不阻断登录，
       *    理由同 `activateNodeWithCode`。
       *
       * @param {string} nodeId
       */
      loginAsActivatedNode(nodeId) {
        const id = String(nodeId || '').trim()
        if (!id) {
          return Promise.reject(new Error('缺少节点编号'))
        }
        this.declaredPrincipal = 'NODE'
        return getNodeChallenge(id)
          .then(async (challenge) => {
            if (!challenge?.challenge || !challenge?.challengeId) {
              throw new Error('服务端未返回有效挑战')
            }
            const signature = await signChallenge(id, challenge.challenge)
            return loginWithDevice({ nodeId: id, challengeId: challenge.challengeId, signature })
          })
          .then((res) => {
            const token = typeof res?.token === 'string' ? res.token.trim() : ''
            if (!token) {
              throw new Error('登录成功但服务器未返回有效令牌')
            }
            setToken(token)
            this.token = token
            return recordNodeLogin(id, { name: res.name }).then(() => ({
              token, nodeId: res.nodeId, name: res.name,
            }))
          })
          .catch((error) => {
            this.clearSession()
            throw error
          })
      }
    }
  })

export default useUserStore
