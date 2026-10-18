import http, { unwrap } from '@/api/pqkds/http'

export const listGroupAgreements = () => http.get('/node-self/group-agreements/').then(unwrap)
export const createGroupAgreement = participantNodeIds => http.post('/node-self/group-agreements/', { participantNodeIds }).then(unwrap)
export const getGroupAgreement = id => http.get(`/node-self/group-agreements/${encodeURIComponent(id)}/`).then(unwrap)
export const actOnGroupAgreement = (id, action, payload = {}) => http.post(
  `/node-self/group-agreements/${encodeURIComponent(id)}/`, { action, ...payload }
).then(unwrap)
