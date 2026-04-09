import request from '@/utils/request'

function normalizeBody(body, headers = {}) {
  if (body == null) {
    return body
  }

  if (typeof body !== 'string') {
    return body
  }

  const contentType = headers['Content-Type'] || headers['content-type'] || ''
  if (!contentType.includes('application/json')) {
    return body
  }

  try {
    return JSON.parse(body)
  } catch {
    return body
  }
}

export function requestJson(base, path, options = {}) {
  const method = (options.method || 'GET').toLowerCase()
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }

  const config = {
    url: `${base}${path}`,
    method,
    headers: {
      ...headers,
      ...(options.auth === false ? { isToken: false } : {})
    }
  }

  if (method === 'get' || method === 'delete') {
    config.params = options.params
  } else {
    config.data = normalizeBody(options.body, headers)
  }

  return request(config)
}
