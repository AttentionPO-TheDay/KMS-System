import request from '@/utils/request'

const generateBaseURL = import.meta.env.VITE_APP_GENERATE_API || '/generate-api'

export function addGenerateKeymanage(data) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/keymanage',
    method: 'post',
    data
  })
}

export function getGenerateComParam(data) {
  return request({
    baseURL: generateBaseURL,
    url: '/generate/keymanage/comparam',
    method: 'post',
    data
  }).then(res => res.data || res)
}
