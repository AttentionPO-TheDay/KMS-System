import { reactive } from 'vue'

const TOKEN_KEY = 'kms-user-token'
const PROFILE_KEY = 'kms-user-profile'

function loadProfile() {
  const raw = window.localStorage.getItem(PROFILE_KEY)
  if (!raw) {
    return null
  }

  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export const authState = reactive({
  token: window.localStorage.getItem(TOKEN_KEY) || '',
  profile: loadProfile(),
  systemAccess: {
    generate: { ok: false, message: '未校验' },
    lifecycle: { ok: false, message: '未校验' },
    distribute: { ok: false, message: '未校验' }
  },
  loading: false,
  ready: false,
  lastError: ''
})

export function persistSession() {
  if (authState.token) {
    window.localStorage.setItem(TOKEN_KEY, authState.token)
  } else {
    window.localStorage.removeItem(TOKEN_KEY)
  }

  if (authState.profile) {
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify(authState.profile))
  } else {
    window.localStorage.removeItem(PROFILE_KEY)
  }
}

export function getAuthToken() {
  return authState.token
}

export function clearSession() {
  authState.token = ''
  authState.profile = null
  authState.systemAccess.generate = { ok: false, message: '未登录' }
  authState.systemAccess.lifecycle = { ok: false, message: '未登录' }
  authState.systemAccess.distribute = { ok: false, message: '未登录' }
  persistSession()
}
