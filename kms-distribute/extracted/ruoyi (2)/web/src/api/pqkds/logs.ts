import request from '@/utils/request'

export const logsApi = {
  // 获取操作日志列表（从系统操作日志）
  getList(params?: any) {
    return request({
      url: '/api/system/operation_log/',
      method: 'get',
      params
    })
  },

  // 获取日志详情
  getDetail(id: number) {
    return request({
      url: `/api/system/operation_log/${id}/`,
      method: 'get'
    })
  },

  // 获取日志统计（获取足够多的数据用于统计）
  getStats() {
    return request({
      url: '/api/system/operation_log/',
      method: 'get',
      params: { limit: 999 }
    })
  }
}
