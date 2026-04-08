export function isHttp(url) {
  return url && (url.startsWith('http://') || url.startsWith('https://'))
}

export function isExternal(path) {
  return /^(https?:|mailto:|tel:)/.test(path)
}

export function isPathMatch(path, pattern) {
  if (!pattern || !path) {
    return false
  }
  if (pattern === path) {
    return true
  }
  const patternParts = pattern.split('/')
  const pathParts = path.split('/')
  if (patternParts.length !== pathParts.length) {
    return false
  }
  for (let i = 0; i < patternParts.length; i++) {
    const patternPart = patternParts[i]
    if (patternPart === '*') {
      continue
    }
    if (patternPart !== pathParts[i]) {
      return false
    }
  }
  return true
}

export function isEmpty(val) {
  return val === undefined || val === null || val === ''
}
