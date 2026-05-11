import request from '@/utils/request'

export const blockchainApi = {
  // 获取区块链状态
  getStatus() {
    return request({
      url: '/api/pqkds/blockchain-config/status/',
      method: 'get'
    })
  },

  // 部署智能合约
  deployContract() {
    return request({
      url: '/api/pqkds/blockchain-config/deploy_contract/',
      method: 'post'
    })
  },

  // 从区块链获取节点信息
  getNodesFromBlockchain() {
    return request({
      url: '/api/pqkds/blockchain-config/nodes_from_blockchain/',
      method: 'get'
    })
  },

  // 获取区块链配置列表
  getConfigList(params?: any) {
    return request({
      url: '/api/pqkds/blockchain-config/',
      method: 'get',
      params
    })
  },

  // 创建区块链配置
  createConfig(data: any) {
    return request({
      url: '/api/pqkds/blockchain-config/',
      method: 'post',
      data
    })
  },

  // 更新区块链配置
  updateConfig(id: number, data: any) {
    return request({
      url: `/api/pqkds/blockchain-config/${id}/`,
      method: 'put',
      data
    })
  },

  // 删除区块链配置
  deleteConfig(id: number) {
    return request({
      url: `/api/pqkds/blockchain-config/${id}/`,
      method: 'delete'
    })
  },

  // 获取当前活跃的区块链配置
  getActiveConfig() {
    return request({
      url: '/api/pqkds/blockchain-config/active/',
      method: 'get'
    })
  },

  // 自动同步：将数据库节点信息同步到区块链
  syncDatabaseToBlockchain() {
    return request({
      url: '/api/pqkds/blockchain-config/sync_database_to_blockchain/',
      method: 'post'
    })
  }
}
