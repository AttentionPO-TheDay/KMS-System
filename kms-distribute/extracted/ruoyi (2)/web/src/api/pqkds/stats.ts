import request from '@/utils/request'

export const statsApi = {
  // 获取系统概览统计
  getOverview() {
    return request({
      url: '/api/pqkds/stats/overview/',
      method: 'get'
    })
  },

  // 获取区块链统计
  getBlockchain() {
    return request({
      url: '/api/pqkds/stats/blockchain/',
      method: 'get'
    })
  }
}
