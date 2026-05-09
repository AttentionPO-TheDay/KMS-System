import request from '@/utils/request'

export const sessionKeysApi = {
  // 获取会话密钥列表
  getList(params?: any) {
    return request({
      url: '/api/pqkds/session-keys/',
      method: 'get',
      params
    })
  },
  // 发送基于会话密钥的消息
  sendMessage(sessionPk: number, data: any) {
    return request({
      url: `/api/pqkds/session-keys/${sessionPk}/send_message/`,
      method: 'post',
      data
    })
  },
  // 解密消息
  decryptMessage(sessionPk: number, data: any) {
    return request({
      url: `/api/pqkds/session-keys/${sessionPk}/decrypt_message/`,
      method: 'post',
      data
    })
  },

  // 获取会话历史消息
  getMessages(sessionPk: number) {
    return request({
      url: `/api/pqkds/session-keys/${sessionPk}/get_messages/`,
      method: 'get'
    })
  },

  // 发起会话密钥交换
  initiate(data: any) {
    return request({
      url: '/api/pqkds/session-keys/initiate/',
      method: 'post',
      data
    })
  },

  // 获取会话密钥详情
  getDetail(id: number) {
    return request({
      url: `/api/pqkds/session-keys/${id}/`,
      method: 'get'
    })
  },

  // 更新会话密钥状态
  updateStatus(id: number, data: any) {
    return request({
      url: `/api/pqkds/session-keys/${id}/`,
      method: 'patch',
      data
    })
  },

  // 删除会话密钥
  delete(id: number) {
    return request({
      url: `/api/pqkds/session-keys/${id}/`,
      method: 'delete'
    })
  }
}
