import request from '@/utils/request'

export const nodesApi = {
  // 获取节点列表
  getList(params?: any) {
    return request({
      url: '/api/pqkds/nodes/',
      method: 'get',
      params
    })
  },

  // 注册新节点
  register(data: any) {
    return request({
      url: '/api/pqkds/nodes/register/',
      method: 'post',
      data
    })
  },

  // 获取节点详情
  getDetail(id: number) {
    return request({
      url: `/api/pqkds/nodes/${id}/`,
      method: 'get'
    })
  },

  // 部分更新节点信息
  partialUpdate(id: number, data: any) {
    return request({
      url: `/api/pqkds/nodes/${id}/`,
      method: 'patch',
      data
    })
  },

  // 生成Falcon密钥对
  generateFalconKeys(id: number) {
    return request({
      url: `/api/pqkds/nodes/${id}/generate_falcon_keys/`,
      method: 'post'
    })
  },

  // 生成Falcon密钥对（支持方案选择）
  generateFalconKeysWithScheme(nodeId: string, scheme: string) {
    return request({
      url: '/api/pqkds/node/generate-falcon-keypair/',
      method: 'post',
      data: {
        node_id: nodeId,
        scheme: scheme
      }
    })
  },

  // 获取节点密钥信息
  getKeys(id: number) {
    return request({
      url: `/api/pqkds/nodes/${id}/keys/`,
      method: 'get'
    })
  },

  // 获取节点密钥详情（包括私钥和部分私钥）
  getKeyDetails(id: string) {
    return request({
      url: `/api/pqkds/nodes/${id}/key_details/`,
      method: 'get'
    })
  },

  // 获取节点统计信息
  getStats() {
    return request({
      url: '/api/pqkds/nodes/stats/',
      method: 'get'
    })
  },

  // 删除节点
  delete(id: number) {
    return request({
      url: `/api/pqkds/nodes/${id}/`,
      method: 'delete'
    })
  },

  // 批量删除节点
  batchDelete(ids: number[]) {
    return request({
      url: '/api/pqkds/nodes/batch_delete/',
      method: 'post',
      data: {
        node_ids: ids
      }
    })
  },

  // 更新节点信息
  update(id: number, data: any) {
    return request({
      url: `/api/pqkds/nodes/${id}/`,
      method: 'put',
      data
    })
  },

  // 更新节点密钥
  updateKeys(id: number, data: {
    key_type: 'kyber' | 'falcon' | 'both'
    kyber_security_level?: number
    falcon_security_level?: number
    falcon_version?: 'v1' | 'v2'
  }) {
    return request({
      url: `/api/pqkds/nodes/${id}/update_keys/`,
      method: 'post',
      data
    })
  }
}
