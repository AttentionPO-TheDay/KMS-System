import {
  getSelfNode, listSelfNodeKeys, registerSelfNodePublicKey, initSelfNodeKeys,
  acquireDemoInitLease, releaseDemoInitLease, issueSelfNodeKeygen,
  renewSelfNodeKeygenAuthorization, listSelfNodeKeygenIssuances, NODE_SELF_ERR
} from '@/api/pqkds/node-self'
import { cryptoProvider } from './crypto/browser-provider.js'
import {
  inspectNodeKeys, requireLocalKey, unsealSecret, readMetaRecord, writeMetaRecord,
  updateGenerationAuthorization
} from './crypto/node-key-store.js'
import {
  publicGeneration, publicGenerationContext, formatGenerationName, GENERATION_SCHEMES
} from './crypto/generation-scheme.js'
import { activeServerKey, findLocalKey, reconcileRow, RECONCILE } from './crypto/node-key-compare.js'
import { buildKeyRef } from './crypto/key-ref.js'
import { deviceFingerprint, hasDeviceKey } from './crypto/device-credential.js'
import { IS_DEMO, ENTRY_MODE } from './entry-mode'
import { getDemoContext } from './demo-context'

export const INITIALIZATION_ALGORITHMS = ['KYBER', 'SSCL', 'SM2', 'FALCON']
const metadataKey = (nodeId, algorithm) => `initialization/${nodeId}/${algorithm}`
const isPQ = algorithm => algorithm === 'KYBER' || algorithm === 'FALCON'

// Public registration fields only. Never serialize generated/private material into meta or requests.
function registrationFields(local, requireGeneration = true) {
  let securityLevel
  if (local.algorithm === 'KYBER') {
    securityLevel = ({ 800: '512', 1184: '768', 1568: '1024' })[String(local.publicKey || '').length / 2]
    if (!securityLevel) throw new Error('KEM 公钥长度无法识别，不能猜测登记参数')
  }
  if (!local.keyId || !Number.isInteger(Number(local.version)) || Number(local.version) < 1 || !local.publicKey) {
    throw new Error('本机材料缺少登记所需的 keyId、版本或公钥，请恢复原材料')
  }
  const fields = {
    keyRef: local.keyRef, algorithm: local.algorithm, keyId: local.keyId,
    version: local.version, publicKey: local.publicKey, securityLevel
  }
  if (isPQ(local.algorithm)) {
    if (!local.generation && requireGeneration) {
      const error = new Error('历史未登记材料的生成来源未记录；需要明确的历史恢复操作，禁止自动换钥或补造双份额来源')
      error.errorCode = NODE_SELF_ERR.KEYGEN_GENERATION_REQUIRED
      throw error
    }
    if (local.generation) {
      fields.generation = publicGeneration(local.generation)
      fields.generationContext = publicGenerationContext(local.generationContext)
    }
  }
  return fields
}

/** Injectable workflow shared by initialization, creation and explicit rotation. */
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
      bytes?.fill(0)
    }
    return summary
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
      let pending = await deps.readMetaRecord(metadataKey(node.nodeId, algorithm))
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
          local = await readable(local, node.nodeId)
          if (!current) {
            // A crash after sealing but before pending must never trigger another KeyGen.
            const fields = registrationFields(local)
            pending = { k: metadataKey(node.nodeId, algorithm), ...fields }
            await deps.writeMetaRecord(pending)
          }
          complete = Boolean(current)
        } catch (error) {
          state = error.errorCode === NODE_SELF_ERR.KEYGEN_GENERATION_REQUIRED ? 'LEGACY_RECOVERY_REQUIRED' : 'LOCAL_UNREADABLE'
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

  async function fingerprintFor(nodeId) {
    if (deps.isDemo) return undefined
    if (!await deps.hasDeviceKey(nodeId)) throw new Error('本机没有节点设备凭据，请返回原设备或重新激活登录')
    const fingerprint = await deps.deviceFingerprint(nodeId)
    if (!fingerprint) throw new Error('无法读取设备公钥指纹，已停止生成')
    return fingerprint
  }

  function identityGuard(nodeId) {
    const context = deps.isDemo ? deps.getDemoContext() : null
    if (deps.isDemo && (!context || context.principalType !== 'NODE' || context.nodeId !== nodeId)) {
      throw new Error('演示节点上下文与当前节点不一致，请重新进入')
    }
    return () => {
      if (deps.isDemo && deps.getDemoContext() !== context) throw new Error('演示身份修订已变化，操作已停止；不会自动换钥或修复来源')
    }
  }

  function trustedIdentity(node, fingerprint, assertIdentity) {
    assertIdentity()
    const identity = node?.keygenIdentity
    const names = ['userId', 'nodeId', 'bindingKind', 'deviceFingerprint', 'demoSessionId', 'demoRevision']
    if (!identity || names.some(name => typeof identity[name] !== 'string') || !/^(0|[1-9][0-9]*)$/.test(identity.userId)) {
      throw new Error('服务器未提供完整可信生成身份快照；请重建升级服务，不会降级生成')
    }
    if (identity.nodeId !== node.nodeId) throw new Error('可信生成身份快照与当前节点不一致；操作已停止')
    if (deps.isDemo ? identity.bindingKind !== 'DEMO' || identity.deviceFingerprint !== '' || !identity.demoSessionId ||
        identity.demoRevision !== String(deps.getDemoContext().revision)
      : identity.bindingKind !== 'DEVICE' || identity.deviceFingerprint !== fingerprint || identity.demoSessionId !== '' || identity.demoRevision !== '') {
      throw new Error('可信生成身份快照与当前设备或演示修订不一致；操作已停止')
    }
    return Object.fromEntries(names.map(name => [name, identity[name]]))
  }

  async function assertSnapshot(nodeId, fingerprint, identity, assertIdentity) {
    assertIdentity()
    const data = await deps.getSelfNode()
    assertIdentity()
    if (!data?.mapped || data.node?.nodeId !== nodeId || data.node.status === 'DISABLED') throw new Error('节点身份或状态已变化；操作已停止')
    const current = trustedIdentity(data.node, fingerprint, assertIdentity)
    if (Object.keys(identity).some(name => current[name] !== identity[name])) {
      throw new Error('可信生成身份上下文已变化；不会自动换钥或修复来源')
    }
  }

  function assertGenerationIdentity(fields, identity) {
    if (fields.generationContext && Object.keys(identity).some(name => fields.generationContext[name] !== identity[name])) {
      throw new Error('已封存密钥属于不同身份、设备或演示修订；请返回原身份恢复，不会续期或换钥')
    }
  }

  async function registerMaterial(local, { nodeId, fingerprint, identity, headers, rotate, assertIdentity }) {
    local = await readable(local, nodeId)
    let fields = registrationFields(local)
    if (fields.generation) assertGenerationIdentity(fields, identity)
    const pendingKey = rotate ? `rotation/${local.keyRef}` : metadataKey(nodeId, local.algorithm)
    await deps.writeMetaRecord({ k: pendingKey, ...fields })
    async function dispatch() {
      assertIdentity()
      if (identity) await assertSnapshot(nodeId, fingerprint, identity, assertIdentity)
      return deps.registerSelfNodePublicKey(local.algorithm, fields.publicKey, fields.securityLevel,
        fingerprint, fields.keyId, fields.version, rotate, headers, { generation: fields.generation })
    }
    try {
      return await dispatch()
    } catch (error) {
      // Only expiry permits renewal; identity/context changes and conflicts never auto-repair.
      if (error.errorCode !== NODE_SELF_ERR.KEYGEN_AUTHORIZATION_EXPIRED || !fields.generation) throw error
      assertIdentity()
      await assertSnapshot(nodeId, fingerprint, identity, assertIdentity)
      const renewed = await deps.renewSelfNodeKeygenAuthorization({
        generationIssuanceId: fields.generation.generationIssuanceId,
        publicKey: fields.publicKey, deviceId: fingerprint
      }, headers)
      assertIdentity()
      if (!renewed?.authorizationTicketId) throw new Error('服务器未返回有效续期授权；已封存材料保留')
      await deps.updateGenerationAuthorization(local.keyRef, renewed.authorizationTicketId)
      local = await readable(local, nodeId)
      fields = registrationFields(local)
      await deps.writeMetaRecord({ k: pendingKey, ...fields })
      return dispatch()
    }
  }

  async function generationOptions(algorithm, options, fingerprint, identity, headers, assertIdentity, confirmUnusedIssuance) {
    if (!isPQ(algorithm)) return options
    await assertSnapshot(options.nodeId, fingerprint, identity, assertIdentity)
    const listing = await deps.listSelfNodeKeygenIssuances(fingerprint, headers)
    assertIdentity()
    if (!Array.isArray(listing?.issuances)) throw new Error('无法安全读取原始签发恢复清单；已停止生成')
    const locals = (await deps.inspectNodeKeys(options.nodeId)).keys || []
    const unused = listing.issuances.filter(record => {
      const context = publicGenerationContext(record.context)
      if (!Number.isSafeInteger(Number(context.keyVersion))) throw new Error('签发恢复版本超出本机安全整数范围')
      if (context.nodeId !== options.nodeId || Object.keys(identity).some(name => context[name] !== identity[name])) throw new Error('签发恢复清单与当前可信身份不一致')
      return context.coreFamily === algorithm && record.status === 'ISSUED' && !record.publicKeyHash &&
        Number(context.keyVersion) === Number(options.version || 1) && (!options.keyId || context.keyId === options.keyId) &&
        !locals.some(local => local.keyRef === buildKeyRef({ nodeId: context.nodeId, algorithm, keyId: context.keyId, version: Number(context.keyVersion) }))
    })
    if (unused.length > 1) throw new Error('存在多份未完成签发，请显式确认原始来源；禁止自动弃用或另起生成')
    const abandoned = unused[0]
    if (abandoned) {
      const context = publicGenerationContext(abandoned.context)
      if (options.keyId && Number(context.variant) !== Number(options.variant || (algorithm === 'FALCON' ? 512 : 768))) {
        throw new Error('未完成签发参数与当前生产版本不一致；禁止改变轮换参数或自动修复')
      }
      options = { ...options, keyId: context.keyId, version: Number(context.keyVersion), variant: Number(context.variant) }
    }
    return {
      ...options, generationContext: { nodeId: options.nodeId, ...identity },
      issueKeygen: async request => {
        await assertSnapshot(options.nodeId, fingerprint, identity, assertIdentity)
        const payload = { algorithm: request.algorithm, keyId: request.keyId, keyVersion: request.keyVersion,
          variant: request.variant, deviceId: fingerprint }
        if (abandoned) {
          const context = publicGenerationContext(abandoned.context)
          if (abandoned.generationIssuanceId !== context.generationIssuanceId || context.keyId !== request.keyId ||
              context.keyVersion !== String(request.keyVersion) || context.variant !== String(request.variant) ||
              !['ISSUED', 'EXPIRED'].includes(abandoned.authorizationStatus)) throw new Error('原始签发已绑定或不能安全弃用；请恢复原材料')
          if (!confirmUnusedIssuance || await confirmUnusedIssuance({
            generationIssuanceId: abandoned.generationIssuanceId, keyId: context.keyId,
            keyVersion: context.keyVersion, label: formatGenerationName(algorithm, context.schemeId), variant: context.variant,
            message: `发现未完成签发 ${abandoned.generationIssuanceId}（${context.keyId} · v${context.keyVersion} · 参数 ${context.variant}）。本机没有对应封存材料，原秘密份额无法恢复。是否明确弃用这次未使用签发并重新发放？会保留 keyId/版本，且不会删除或覆盖任何已有私钥。`
          }) !== true) throw new Error('已取消弃用原始签发；未产生新的服务端秘密贡献')
          await assertSnapshot(options.nodeId, fingerprint, identity, assertIdentity)
          const existing = (await deps.inspectNodeKeys(options.nodeId)).keys || []
          const ref = buildKeyRef({ nodeId: options.nodeId, algorithm, keyId: request.keyId, version: request.keyVersion })
          const pending = await deps.readMetaRecord(options.rotate ? `rotation/${ref}` : metadataKey(options.nodeId, algorithm))
          if (existing.some(local => local.keyRef === ref) || pending?.keyRef === ref) throw new Error('原始签发已有本机封存或待登记记录；禁止弃用、换钥或覆盖')
          payload.abandonGenerationIssuanceId = abandoned.generationIssuanceId
        }
        const issuance = await deps.issueSelfNodeKeygen(payload, headers)
        await assertSnapshot(options.nodeId, fingerprint, identity, assertIdentity)
        return issuance
      }
    }
  }

  async function initializeNode({ onProgress = () => {}, confirmUnusedIssuance } = {}) {
    if (!deps.locks?.request) throw new Error('当前浏览器不支持 Web Locks；为避免覆盖密钥，初始化已关闭')
    const initial = await deps.getSelfNode()
    const nodeId = initial?.mapped && initial?.node?.nodeId
    if (!nodeId) throw new Error('当前身份未关联节点')
    const assertIdentity = identityGuard(nodeId)
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
        const fingerprint = await fingerprintFor(nodeId)
        const identity = trustedIdentity(inspection.node, fingerprint, assertIdentity)
        for (const step of inspection.algorithms) {
          assertIdentity()
          const source = step.server || step.local
          const label = formatGenerationName(step.algorithm, source ? source.generation : GENERATION_SCHEMES[step.algorithm])
          if (step.complete) {
            onProgress({ algorithm: step.algorithm, status: 'complete', message: `${label} 已登记且本机可读，跳过` })
            continue
          }
          let local = step.local
          if (!local) {
            onProgress({ algorithm: step.algorithm, status: 'generating', message: `正在生成 ${label}…` })
            const options = await generationOptions(step.algorithm,
              { nodeId, version: 1, ...(step.algorithm === 'KYBER' ? { variant: 768 } : {}) },
              fingerprint, identity, headers, assertIdentity, confirmUnusedIssuance)
            local = await deps.generate(step.algorithm, options)
          }
          onProgress({ algorithm: step.algorithm, status: 'registering', message: `正在登记 ${label} 公钥（复用已封存材料）…` })
          await registerMaterial(local, { nodeId, fingerprint, identity, headers, assertIdentity })
          onProgress({ algorithm: step.algorithm, status: 'complete', message: `${label} 公钥已登记` })
        }
        assertIdentity()
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
          try { await deps.releaseDemoInitLease(leaseId) } catch {
            // Changed/expired revisions may reject release; server expiry is authoritative.
          }
        }
      }
    })
  }

  async function generateAndRegisterNodeKey({ algorithm, nodeId, keyId, version = 1, variant, rotate = false, confirmUnusedIssuance }) {
    if (!deps.locks?.request) throw new Error('当前浏览器不支持 Web Locks；为避免覆盖密钥，生成已关闭')
    const assertIdentity = identityGuard(nodeId)
    // Same per-node lock as initialization: no tab can create another pending key in parallel.
    return deps.locks.request(`kms-init/${deps.entryMode}/${nodeId}`, { mode: 'exclusive', ifAvailable: true }, async lock => {
      if (!lock) throw new Error('另一标签页正在生成或初始化，请等待完成后刷新')
      assertIdentity()
      const current = await deps.getSelfNode()
      if (!current?.mapped || current.node?.nodeId !== nodeId || current.node.status !== 'ACTIVE') {
        throw new Error('节点身份或状态已变化；请先完成初始化或刷新')
      }
      const fingerprint = await fingerprintFor(nodeId)
      const identity = isPQ(algorithm) ? trustedIdentity(current.node, fingerprint, assertIdentity) : null
      const response = await deps.listSelfNodeKeys()
      if (response?.nodeId !== nodeId || !Array.isArray(response.keys)) throw new Error('节点公钥清单与当前身份不一致')
      const localKeys = (await deps.inspectNodeKeys(nodeId)).keys || []
      if (rotate) {
        const active = activeServerKey(response.keys, algorithm)
        const existing = active && findLocalKey(localKeys, { algorithm, keyId: active.keyId, version: active.keyVersion })
        if (!active || active.keyId !== keyId || Number(active.keyVersion) + 1 !== Number(version) ||
            reconcileRow(active, existing).state !== RECONCILE.MATCH) throw new Error('生产版本已变化或本机材料不匹配；禁止基于旧页面换钥')
        await readable(existing, nodeId)
      }
      const candidates = localKeys.filter(local => local.algorithm === algorithm && (rotate
        ? local.keyId === keyId && Number(local.version) === Number(version)
        : !response.keys.some(server => server.algorithm === algorithm && server.keyId === local.keyId && Number(server.keyVersion) === Number(local.version))))
      if (candidates.length > 1) throw new Error('存在多份未登记材料，请显式恢复原材料；禁止生成替代')
      const pendingKey = rotate ? `rotation/${buildKeyRef({ nodeId, algorithm, keyId, version })}` : metadataKey(nodeId, algorithm)
      const pending = await deps.readMetaRecord(pendingKey)
      const pendingRegistered = pending && response.keys.some(server => server.algorithm === algorithm &&
        server.keyId === pending.keyId && Number(server.keyVersion) === Number(pending.version) && server.publicKey === pending.publicKey)
      if (pending && !pendingRegistered && (!candidates[0] || candidates[0].keyRef !== pending.keyRef ||
          candidates[0].keyId !== pending.keyId || Number(candidates[0].version) !== Number(pending.version) || candidates[0].publicKey !== pending.publicKey)) {
        throw new Error('待登记材料缺失或已变化，请恢复原本机材料；禁止生成另一把替代')
      }
      let material = candidates[0]
      const reused = Boolean(material)
      if (material) {
        material = await readable(material, nodeId)
        registrationFields(material)
      } else {
        const options = await generationOptions(algorithm,
          { nodeId, keyId, version, variant, rotate }, fingerprint, identity, undefined, assertIdentity, confirmUnusedIssuance)
        material = await deps.generate(algorithm, options)
      }
      material = await readable(material, nodeId)
      registrationFields(material)
      // Sealed record is authoritative even if the pending write fails.
      await deps.writeMetaRecord({ k: rotate ? `rotation/${material.keyRef}` : metadataKey(nodeId, algorithm), ...registrationFields(material) })
      assertIdentity()
      const check = await deps.selfTest(algorithm, material.keyRef)
      if (!check.ok) throw new Error(`新材料已封存，但自检未过：${check.detail}；未登记，平台生产版本不变，重试复用原材料`)
      const result = await registerMaterial(material, { nodeId, fingerprint, identity, rotate, assertIdentity })
      return { material, result, check, reused }
    })
  }
  return { inspectInitialization, initializeNode, generateAndRegisterNodeKey }
}

const service = createNodeInitializationService({
  getSelfNode, listSelfNodeKeys, registerSelfNodePublicKey, initSelfNodeKeys,
  acquireDemoInitLease, releaseDemoInitLease, issueSelfNodeKeygen, renewSelfNodeKeygenAuthorization,
  listSelfNodeKeygenIssuances, inspectNodeKeys, requireLocalKey, unsealSecret, readMetaRecord, writeMetaRecord,
  updateGenerationAuthorization, deviceFingerprint, hasDeviceKey,
  generate: (algorithm, options) => cryptoProvider.generate(algorithm, options),
  selfTest: (algorithm, keyRef) => cryptoProvider.selfTest(algorithm, keyRef),
  isDemo: IS_DEMO, entryMode: ENTRY_MODE, getDemoContext, locks: globalThis.navigator?.locks
})
export const inspectInitialization = service.inspectInitialization
export const initializeNode = service.initializeNode
export const generateAndRegisterNodeKey = service.generateAndRegisterNodeKey
