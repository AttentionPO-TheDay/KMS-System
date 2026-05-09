import request from '@/utils/request'

// 区块链集成的Falcon无证书密钥分发API

/**
 * 初始化区块链Falcon系统
 */
export function setupBlockchainFalconSystem(data) {
  return request({
    url: '/pqkds/blockchain/setup/',
    method: 'post',
    data: data
  })
}

/**
 * 注册节点并生成Falcon密钥（区块链集成）
 */
export function registerNodeWithBlockchain(data) {
  return request({
    url: '/pqkds/blockchain/register-node/',
    method: 'post',
    data: data
  })
}

/**
 * 获取节点的Falcon密钥信息
 */
export function getNodeFalconKeys(nodeId) {
  return request({
    url: `/pqkds/blockchain/nodes/${nodeId}/keys/`,
    method: 'get'
  })
}

/**
 * 验证Falcon密钥完整性
 */
export function verifyFalconKeyIntegrity(data) {
  return request({
    url: '/pqkds/blockchain/verify-integrity/',
    method: 'post',
    data: data
  })
}

/**
 * 获取区块链连接状态
 */
export function getBlockchainStatus() {
  return request({
    url: '/pqkds/blockchain/status/',
    method: 'get'
  })
}

/**
 * 列出所有Falcon节点
 */
export function listFalconNodes() {
  return request({
    url: '/pqkds/blockchain/nodes/',
    method: 'get'
  })
}

// 传统PQKDS API（保持兼容性）

/**
 * 初始化系统
 */
export function initializeSystem(data) {
  return request({
    url: '/pqkds/system/initialize/',
    method: 'post',
    data: data
  })
}

/**
 * 获取系统状态
 */
export function getSystemStatus() {
  return request({
    url: '/pqkds/system/status/',
    method: 'get'
  })
}

/**
 * 注册节点
 */
export function registerNode(data) {
  return request({
    url: '/pqkds/node/register/',
    method: 'post',
    data: data
  })
}

/**
 * 生成部分密钥
 */
export function generatePartialKey(data) {
  return request({
    url: '/pqkds/kgc/generate-partial-key/',
    method: 'post',
    data: data
  })
}

/**
 * 生成Falcon密钥对
 */
export function generateFalconKeypair(data) {
  return request({
    url: '/pqkds/node/generate-falcon-keypair/',
    method: 'post',
    data: data
  })
}

/**
 * 发起会话密钥交换
 */
export function initiateSessionKeyExchange(data) {
  return request({
    url: '/pqkds/session/initiate/',
    method: 'post',
    data: data
  })
}
