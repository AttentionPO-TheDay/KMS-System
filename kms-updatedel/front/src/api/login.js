import request from '@/utils/request'

// 登录方法
export function login(username, password, code, uuid) {
  const data = {
    username,
    password,
    code,
    uuid
  }
  return request({
    url: '/login',
    headers: {
      isToken: false,
      repeatSubmit: false
    },
    method: 'post',
    data: data
  })
}

// 注册方法已删除（阶段 9 清理）。
//
// 它对应 `views/register.vue` 那个页面，而该页面与本系统的模型冲突：
// 文档 §2.1/§2.3 明确「节点不能自助注册」，只能由管理员创建后再由节点登录。
// 页面本身既没有路由注册、也不在任何菜单里（阶段 9 已核实），
// 页与这个导出一起删掉。
//
// 保留这段注释而不是直接删干净，是为了让后来搜索 `/register` 的人
// 知道它**是有意去掉的**，不是漏了 —— 否则很容易照 RuoYi 的习惯再加回来。

// 获取用户详细信息
export function getInfo() {
  return request({
    url: '/getInfo',
    method: 'get'
  })
}

// 退出方法
export function logout() {
  return request({
    url: '/logout',
    method: 'post'
  })
}

// 获取验证码
export function getCodeImg() {
  return request({
    url: '/captchaImage',
    headers: {
      isToken: false
    },
    method: 'get',
    timeout: 20000
  })
}