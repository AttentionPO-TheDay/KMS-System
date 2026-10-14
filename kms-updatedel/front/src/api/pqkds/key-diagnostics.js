import http, { unwrap } from '@/api/pqkds/http'

export const getOwnNodeKeyHealth = (keyId, version) => http.get('/node-self/key-health/', { params: { keyId, version } }).then(unwrap)
export const getOwnNodeKeyAnalysis = (keyId, version) => http.get('/node-self/key-analysis/', { params: { keyId, version } }).then(unwrap)
