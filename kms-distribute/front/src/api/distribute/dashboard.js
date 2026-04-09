import request from '@/utils/request'

export function getDashboardOverview() {
  return request({
    url: '/distribute/dashboard/overview',
    method: 'get'
  })
}
