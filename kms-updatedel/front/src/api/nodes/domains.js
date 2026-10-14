import http, { unwrap } from '@/api/pqkds/http'

export const listDomains = () => http.get('/domains/').then(unwrap)
export const createDomain = data => http.post('/domains/', data).then(unwrap)
