const apiBase = import.meta.env.VITE_APP_ACCEPTANCE_API || '/acceptance-api'

async function fetchJson(url, options = {}) {
  const res = await fetch(`${apiBase}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  })
  const payload = await res.json()
  if (!res.ok) {
    throw new Error(payload.message || payload.error || 'Request Failed')
  }
  return payload
}

export const API = {
  getHealth: () => fetchJson('/health'),
  getScenarios: () => fetchJson('/scenarios'),
  getRuns: () => fetchJson('/runs'),
  postRun: (data) => fetchJson('/runs', { method: 'POST', body: JSON.stringify(data) }),
  
  getSecurityRuns: () => fetchJson('/security/runs'),
  postSecurityRun: (data) => fetchJson('/security/runs', { method: 'POST', body: JSON.stringify(data) }),

  getProofRuns: () => fetchJson('/proof/runs'),
  postProofRun: (data) => fetchJson('/proof/runs', { method: 'POST', body: JSON.stringify(data) })
}
