import { getToken, removeToken } from '@/utils/auth'

async function parseResponse(response) {
  const text = await response.text()
  if (!text) {
    return null
  }

  try {
    return JSON.parse(text)
  } catch {
    return { msg: text }
  }
}

export async function requestJson(base, path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }

  const token = getToken()
  if (options.auth !== false && token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`${base}${path}`, {
    ...options,
    headers
  })

  const data = await parseResponse(response)
  if (!response.ok || (data && data.code !== undefined && data.code !== 200)) {
    const message = data?.msg || `请求失败(${response.status})`
    if (response.status === 401 || data?.code === 401) {
      removeToken()
    }
    throw new Error(message)
  }

  return data
}
