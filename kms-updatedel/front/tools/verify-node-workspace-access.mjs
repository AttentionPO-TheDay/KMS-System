import assert from 'node:assert/strict'
import { canEnterNodeWorkspace, classifyUnavailableAlgorithm } from '../src/utils/node-workspace-access.js'

const base = {
  mapped: true,
  node: { status: 'ACTIVE' },
  algorithms: ['KYBER', 'SSCL', 'SM2', 'FALCON'].map(algorithm => ({ algorithm, complete: true }))
}

assert.equal(canEnterNodeWorkspace(base), true, '四套材料完整的已激活节点应进入工作台')

const oneRevoked = structuredClone(base)
oneRevoked.algorithms[2] = {
  algorithm: 'SM2', complete: false, lifecycleUnavailable: true, state: 'REVOKED'
}
assert.equal(canEnterNodeWorkspace(oneRevoked), true, '回收一把密钥不应阻断整个工作台')
assert.deepEqual(
  classifyUnavailableAlgorithm([{ status: 'REVOKED', allowsNewWork: false }], 'ACTIVE')?.state,
  'REVOKED',
  '已回收登记应被识别为生命周期终态，而不是材料缺失'
)
assert.equal(
  classifyUnavailableAlgorithm([{ status: 'ACTIVE', allowsNewWork: true }], 'ACTIVE'),
  null,
  '仍有可用版本时必须继续执行本机材料精确对账'
)

const localMissing = structuredClone(base)
localMissing.algorithms[2] = {
  algorithm: 'SM2', complete: false, lifecycleUnavailable: false, blocked: true, state: 'LOCAL_MISSING'
}
assert.equal(canEnterNodeWorkspace(localMissing), false, '服务端密钥仍可用但本机材料缺失时必须继续阻断')

assert.equal(canEnterNodeWorkspace({ ...base, node: { status: 'PENDING_INIT' } }), false,
  '未完成首次初始化的节点不得进入工作台')
assert.equal(canEnterNodeWorkspace({ ...base, node: { status: 'DISABLED' } }), false,
  '已停用节点不得进入工作台')

console.log('node workspace access checks passed')
