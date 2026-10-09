import Cookies from 'js-cookie'

import { IS_DEMO } from './entry-mode'

const TokenKey = 'Admin-Token'

export function getToken() {
  return IS_DEMO ? undefined : Cookies.get(TokenKey)
}

export function setToken(token) {
  if (IS_DEMO) throw new Error('演示模式不能写入独立运行登录令牌')
  return Cookies.set(TokenKey, token)
}

export function removeToken() {
  if (!IS_DEMO) return Cookies.remove(TokenKey)
}
