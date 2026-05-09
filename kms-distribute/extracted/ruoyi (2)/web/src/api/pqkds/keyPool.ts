import request from '@/utils/request'

export const keyPoolApi = {
  // 获取预分配密钥列表
  getList(params?: any) {
    return request({
      url: '/api/pqkds/key-pool/',
      method: 'get',
      params
    })
  },

  // 批量预分配密钥
  generate(data: {
    node1_id: string
    node2_id: string
    algorithm: 'kyber_kem' | 'falcon_lattice'
    count?: number
    expiry_hours?: number
  }) {
    return request({
      url: '/api/pqkds/key-pool/generate/',
      method: 'post',
      data
    })
  },

  // 取用一条预分配密钥
  consume(data: { node1_id: string; node2_id: string; algorithm?: string }) {
    return request({
      url: '/api/pqkds/key-pool/consume/',
      method: 'post',
      data
    })
  },

  // 获取密钥池统计
  getStats(params?: { node1_id?: string; node2_id?: string }) {
    return request({
      url: '/api/pqkds/key-pool/stats/',
      method: 'get',
      params
    })
  },

  // 清理过期密钥
  cleanup() {
    return request({
      url: '/api/pqkds/key-pool/cleanup/',
      method: 'post'
    })
  },

  // 检查并补充密钥池
  replenish(data: {
    node1_id: string
    node2_id: string
    algorithm?: string
    target_size?: number
  }) {
    return request({
      url: '/api/pqkds/key-pool/replenish/',
      method: 'post',
      data
    })
  },

  // 删除预分配密钥
  delete(id: number) {
    return request({
      url: `/api/pqkds/key-pool/${id}/`,
      method: 'delete'
    })
  },

  // 批量删除预分配密钥
  batchDelete(ids: number[]) {
    return request({
      url: '/api/pqkds/key-pool/batch_delete/',
      method: 'post',
      data: { ids }
    })
  },

  // ========== 线上预分配（单向密钥池，下发到发送方节点本地） ==========

  // 生成单向密钥池（sender → receiver），仅用发送方 Kyber 公钥加密
  distribute(data: {
    sender_node_id: string
    receiver_node_id: string
    count?: number
    expiry_hours?: number
  }) {
    return request({
      url: '/api/pqkds/key-pool/distribute/',
      method: 'post',
      data
    })
  },

  // 发送方节点接收加密的密钥池数据包（Kyber 解密后保存到本地文件）
  receive(data: {
    node_id: string
    encrypted_package: any
  }) {
    return request({
      url: '/api/pqkds/key-pool/receive/',
      method: 'post',
      data
    })
  },

  // 获取节点本地密钥池统计
  getLocalStats(params: { node_id: string }) {
    return request({
      url: '/api/pqkds/key-pool/local_stats/',
      method: 'get',
      params
    })
  }
}
