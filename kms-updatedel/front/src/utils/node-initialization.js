import {
  getSelfNode, listSelfNodeKeys, registerSelfNodePublicKey, initSelfNodeKeys,
  acquireDemoInitLease, releaseDemoInitLease
} from '@/api/pqkds/node-self'
import { cryptoProvider } from './crypto/browser-provider.js'
import {
  inspectNodeKeys, requireLocalKey, unsealSecret, readMetaRecord, writeMetaRecord
} from './crypto/node-key-store.js'
import { activeServerKey, findLocalKey, reconcileRow, RECONCILE } from './crypto/node-key-compare.js'
import { deviceFingerprint, hasDeviceKey } from './crypto/device-credential.js'
import { IS_DEMO, ENTRY_MODE } from './entry-mode'
import { getDemoContext } from './demo-context'

export const INITIALIZATION_ALGORITHMS = ['KYBER', 'SSCL', 'SM2', 'FALCON']
const metadataKey = (nodeId, algorithm) => `initialization/${nodeId}/${algorithm}`

// Public registration fields only. Never serialize generated/private material into meta or requests.
function registrationFields(local) {
  let securityLevel
  if (local.algorithm === 'KYBER') {
    securityLevel = ({ 800: '512', 1184: '768', 1568: '1024' })[String(local.publicKey || '').length / 2]
    if (!securityLevel) throw new Error('Kyber 公钥长度无法识别，不能猜测登记参数')
  }
  if (!local.keyId || !Number.isInteger(Number(local.version)) || Number(local.version) < 1 || !local.publicKey) {
    throw new Error('本机材料缺少登记所需的 keyId、版本或公钥，请恢复原材料')
  }
  return {
    keyRef: local.keyRef, algorithm: local.algorithm, keyId: local.keyId,
    version: local.version, publicKey: local.publicKey, securityLevel
  }
}

/** Dependencies are injectable so retry/locking invariants can be tested without key generation. */
export function createNodeInitializationService(deps) {
  async function readable(local, nodeId) {
    const summary = await deps.requireLocalKey(local.keyRef, {
      nodeId, algorithm: local.algorithm, version: local.version
    })
    if (summary.keyId !== local.keyId || summary.publicKey !== local.publicKey) {
      throw new Error('本机密钥元信息已变化，请恢复与登记公钥对应的原材料')
    }
    const bytes = await deps.unsealSecret(local.keyRef)
    try {
      if (!bytes?.length) throw new Error('本机私钥材料为空')
    } finally {
      // Inspection retains no private material.
      bytes?.fill(0)
    }
  }

  async function inspectInitialization() {
    const data = await deps.getSelfNode()
    const node = data?.node || {}
    const mapped = Boolean(data?.mapped && node.nodeId)
    if (!mapped) return { node, mapped: false, ready: false, blocked: true, algorithms: [], reasons: ['当前身份未关联节点'] }
    const response = await deps.listSelfNodeKeys()
    if (response?.nodeId !== node.nodeId || !Array.isArray(response?.keys)) {
      throw new Error('节点公钥清单与当前身份不一致，已停止初始化')
    }
    const serverKeys = response.keys
    const localKeys = (await deps.inspectNodeKeys(node.nodeId)).keys || []
    const algorithms = []
    for (const algorithm of INITIALIZATION_ALGORITHMS) {
      const rows = serverKeys.filter(row => row.algorithm === algorithm)
      const current = activeServerKey(serverKeys, algorithm)
      const pending = await deps.readMetaRecord(metadataKey(node.nodeId, algorithm))
      let local = current ? findLocalKey(localKeys, {
        algorithm, keyId: current.keyId, version: current.keyVersion
      }) : null
      let state = current ? reconcileRow(current, local).state : 'MISSING'
      let reason = ''
      let blocked = false
      let complete = false
      if (current) {
        blocked = state !== RECONCILE.MATCH
        reason = blocked ? `${algorithm}：${reconcileRow(current, local).text}` : ''
      } else if (rows.length || node.keys?.[algorithm.toLowerCase()] || node.status === 'ACTIVE') {
        // Registered history/materialized columns are not permission to replace the production key.
        blocked = true
        state = 'SERVER_UNUSABLE'
        reason = `${algorithm}：没有可精确对账的当前可用登记版本，禁止自动重建`
      } else {
        const candidates = localKeys.filter(row => row.algorithm === algorithm)
        if (pending) {
          local = candidates.find(row => row.keyRef === pending.keyRef) || null
          if (!local || pending.algorithm !== algorithm || pending.keyId !== local.keyId ||
              Number(pending.version) !== Number(local.version) || pending.publicKey !== local.publicKey) {
            blocked = true
            state = 'PENDING_MISMATCH'
            reason = `${algorithm}：待登记材料缺失或已变化，不能生成另一把替代`
          }
        } else if (candidates.length > 1) {
          blocked = true
          state = 'LOCAL_AMBIGUOUS'
          reason = `${algorithm}：存在多份未登记本机材料，请显式确认或恢复原材料`
        } else {
          local = candidates[0] || null
        }
        if (local && !blocked) state = RECONCILE.LOCAL_ONLY
      }
      if (local && !blocked) {
        try {
          await readable(local, node.nodeId)
          if (!current) registrationFields(local)
          complete = Boolean(current)
        } catch (error) {
          state = 'LOCAL_UNREADABLE'
          blocked = true
          reason = `${algorithm}：${error.message}`
        }
      }
      algorithms.push({ algorithm, server: current, local, pending, state, complete, blocked, reason })
    }
    const reasons = algorithms.filter(row => row.blocked).map(row => row.reason)
    if (node.status === 'DISABLED') reasons.unshift('节点已停用，不能初始化')
    return {
      node, mapped, algorithms, serverKeys, localKeys, reasons,
      blocked: reasons.length > 0,
      ready: node.status === 'ACTIVE' && algorithms.every(row => row.complete)
    }
  }

  async function initializeNode({ onProgress = () => {} } = {}) {
    if (!deps.locks?.request) throw new Error('当前浏览器不支持 Web Locks；为避免覆盖密钥，初始化已关闭')
    const initial = await deps.getSelfNode()
    const nodeId = initial?.mapped && initial?.node?.nodeId
    if (!nodeId) throw new Error('当前身份未关联节点')
    const context = deps.isDemo ? deps.getDemoContext() : null
    if (deps.isDemo && (!context || context.principalType !== 'NODE' || context.nodeId !== nodeId)) {
      throw new Error('演示节点上下文与初始化节点不一致，请重新进入')
    }
    function assertIdentity() {
      if (deps.isDemo && deps.getDemoContext() !== context) throw new Error('演示身份已变化，初始化已停止')
    }
    return deps.locks.request(`kms-init/${deps.entryMode}/${nodeId}`, { mode: 'exclusive', ifAvailable: true }, async lock => {
      if (!lock) throw new Error('另一标签页正在初始化该节点，请等待完成后刷新')
      let leaseId
      try {
        assertIdentity()
        if (deps.isDemo) {
          leaseId = (await deps.acquireDemoInitLease())?.leaseId
          if (!leaseId) throw new Error('服务器未授予初始化租约，已停止')
        }
        const headers = leaseId ? { 'X-Kms-Demo-Init-Lease': leaseId } : undefined
        let inspection = await inspectInitialization()
        if (inspection.node.nodeId !== nodeId) throw new Error('节点身份已变化，已停止初始化')
        if (inspection.blocked) throw new Error(inspection.reasons.join('；'))
        if (inspection.ready) return inspection
        let fingerprint
        if (!deps.isDemo) {
          if (!await deps.hasDeviceKey(nodeId)) throw new Error('本机没有节点设备凭据，请返回原设备或重新激活登录')
          fingerprint = await deps.deviceFingerprint(nodeId)
          if (!fingerprint) throw new Error('无法读取设备公钥指纹，已停止初始化')
        }
        for (const step of inspection.algorithms) {
          assertIdentity()
          if (step.complete) {
            onProgress({ algorithm: step.algorithm, status: 'complete', message: `${step.algorithm} 已登记且本机可读，跳过` })
            continue
          }
          let local = step.local
          if (!local) {
            onProgress({ algorithm: step.algorithm, status: 'generating', message: `正在生成 ${step.algorithm}…` })
            local = await deps.generate(step.algorithm, { nodeId, ...(step.algorithm === 'KYBER' ? { variant: 768 } : {}) })
          }
          await readable(local, nodeId)
          const fields = registrationFields(local)
          // Written before dispatch; even an unknown/failed registration result reuses this exact ref.
          await deps.writeMetaRecord({ k: metadataKey(nodeId, step.algorithm), ...fields })
          assertIdentity()
          onProgress({ algorithm: step.algorithm, status: 'registering', message: `正在登记 ${step.algorithm} 公钥（复用已封存材料）…` })
          await deps.registerSelfNodePublicKey(step.algorithm, fields.publicKey, fields.securityLevel,
            fingerprint, fields.keyId, fields.version, undefined, headers)
          onProgress({ algorithm: step.algorithm, status: 'complete', message: `${step.algorithm} 公钥已登记` })
        }
        assertIdentity()
        // Re-fetch production versions before finishing, not merely the responses to our POSTs.
        inspection = await inspectInitialization()
        if (inspection.node.nodeId !== nodeId || inspection.blocked || !inspection.algorithms.every(row => row.complete)) {
          throw new Error(inspection.reasons.join('；') || '四套登记公钥尚未与本机材料精确匹配')
        }
        onProgress({ algorithm: 'FINISH', status: 'finishing', message: '四套公钥齐备，正在收尾…' })
        await deps.initSelfNodeKeys(headers)
        const final = await inspectInitialization()
        if (final.node.nodeId !== nodeId || !final.ready) throw new Error('初始化收尾后仍未通过四套材料对账，请刷新检查')
        onProgress({ algorithm: 'FINISH', status: 'complete', message: '初始化完成' })
        return final
      } finally {
        if (leaseId) {
          try { await deps.releaseDemoInitLease(leaseId) } catch (error) {
            // A changed/expired revision can reject release; server expiry remains authoritative.
            console.warn('[node-init] 释放初始化租约失败：', error?.message)
          }
        }
      }
    })
  }
  return { inspectInitialization, initializeNode }
}

const service = createNodeInitializationService({
  getSelfNode, listSelfNodeKeys, registerSelfNodePublicKey, initSelfNodeKeys,
  acquireDemoInitLease, releaseDemoInitLease, inspectNodeKeys, requireLocalKey,
  unsealSecret, readMetaRecord, writeMetaRecord, deviceFingerprint, hasDeviceKey,
  generate: (algorithm, options) => cryptoProvider.generate(algorithm, options),
  isDemo: IS_DEMO, entryMode: ENTRY_MODE, getDemoContext, locks: globalThis.navigator?.locks
})
export const inspectInitialization = service.inspectInitialization
export const initializeNode = service.initializeNode
