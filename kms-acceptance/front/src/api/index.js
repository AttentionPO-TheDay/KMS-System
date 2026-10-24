import { acceptanceFetch } from './demo-context.js'

function fetchJson(url, options = {}) {
  return acceptanceFetch(url, options)
}

export const API = {
  getLattice: () => fetchJson('/lattice'),
  runLattice: data => fetchJson('/lattice', { method: 'POST', body: JSON.stringify(data) }),
  getHealth: () => fetchJson('/health'),
  getScenarios: () => fetchJson('/scenarios'),
  getRuns: () => fetchJson('/runs'),
  getRun: id => fetchJson(`/runs/${encodeURIComponent(id)}`),
  cancelRun: id => fetchJson(`/runs/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }),
  postRun: (data) => fetchJson('/runs', { method: 'POST', body: JSON.stringify(data) }),
  
  getSecurityRuns: () => fetchJson('/security/runs'),
  getSecurityRun: id => fetchJson(`/security/runs/${encodeURIComponent(id)}`),
  postSecurityRun: (data) => fetchJson('/security/runs', { method: 'POST', body: JSON.stringify(data) }),
  cancelSecurityRun: id => fetchJson(`/security/runs/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }),

  getProofRuns: () => fetchJson('/proof/runs'),
  postProofRun: (data) => fetchJson('/proof/runs', { method: 'POST', body: JSON.stringify(data) }),

  getAcceptanceCriteria: () => fetchJson('/acceptance/criteria'),
  getAcceptanceEvidence: () => fetchJson('/acceptance/evidence'),
  postAcceptanceEvidence: (data) => fetchJson('/acceptance/evidence', { method: 'POST', body: JSON.stringify(data) })
}
