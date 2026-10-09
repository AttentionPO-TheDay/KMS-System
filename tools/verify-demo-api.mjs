/** 双入口验收：真 Demo Cookie/上下文/审批/密码学会话，不替换业务服务。
 * 仅本机测试，节点采用唯一前缀并自建自清。--disabled 验证默认关闭。
 */
import { cryptoProvider, makeReporter, isOk } from '../kms-updatedel/front/tools/lib/node-session.mjs'
import { sqlScalar } from './lib/mysql.mjs'
const ORIGIN = 'http://127.0.0.1:8088'
const { check, finish } = makeReporter()
const seed = Date.now().toString(36).toUpperCase()
const names = [`Demo-API-A-${seed}`, `Demo-API-B-${seed}`]
const table = 'falcon_kds.dvadmin_pqkds_nodes'

class DemoSession {
  cookie = ''; context = null
  async call(base, path, { method = 'GET', body, headers = {} } = {}) {
    const response = await fetch(`${ORIGIN}/demo-api/${base}${path}`, {
      method, headers: {
        'Content-Type': 'application/json', Origin: ORIGIN,
        ...(this.cookie ? { Cookie: this.cookie } : {}),
        ...(this.context?.csrfToken ? { 'X-Kms-Demo-CSRF': this.context.csrfToken } : {}),
        ...(this.context?.revision !== undefined ? { 'X-Kms-Demo-Revision': String(this.context.revision) } : {}),
        ...headers
      }, ...(body !== undefined ? { body: JSON.stringify(body) } : {})
    })
    const cookie = response.headers.getSetCookie?.().find(x => x.startsWith('KMS-Demo-Session='))
    if (cookie) this.cookie = cookie.split(';')[0]
    const data = await response.json().catch(() => null)
    return { status: response.status, body: data, cookieHeader: cookie }
  }
  async switch(path, body = {}) {
    const res = await this.call('lifecycle', `/demo/context${path}`, { method: 'POST', body })
    if (isOk(res.body)) this.context = res.body.data
    return res
  }
  work(path, options) { return this.call('pqkds', path, options) }
}
const requireOk = (res, label) => {
  if (!isOk(res.body)) throw new Error(`${label}: HTTP=${res.status} ${JSON.stringify(res.body)}`)
  return res.body.data
}

if (process.argv.includes('--disabled')) {
  for (const path of ['/demo', '/updatedel/demo', '/demo-api/lifecycle/demo/context', '/demo-api/pqkds/node-self/']) {
    const res = await fetch(`${ORIGIN}${path}`, { redirect: 'manual' })
    check(`关闭时 ${path} 不可用`, res.status === 404, `HTTP=${res.status}`)
  }
  finish()
} else {
  const admin = new DemoSession(), a = new DemoSession(), b = new DemoSession()
  const createdNodes = []
  try {
    let res = await admin.switch('/admin')
    requireOk(res, '建立演示管理员')
    check('管理员是独立 DEMO_ADMIN，无 nodeId', admin.context.principalType === 'ADMIN' && !admin.context.nodeId)
    check('只有独立 HttpOnly Cookie，没有普通登录 Token',
      /HttpOnly/i.test(res.cookieHeader || '') && !res.body.token && !res.body.data.token)
    res = await new DemoSession().work('/admin/node-authorization-requests/')
    check('没有 Demo Cookie 不能管理', !isOk(res.body), `HTTP=${res.status}`)
    res = await admin.work('/admin/node-authorization-requests/', { headers: { 'X-Kms-Demo-Revision': '999999' } })
    check('伪造上下文版本被拒', !isOk(res.body), `HTTP=${res.status}`)
    res = await admin.work('/nodes/register/', { method: 'POST', body: {}, headers: { 'X-Kms-Demo-CSRF': '' } })
    check('变更请求缺少 CSRF 被拒', !isOk(res.body), `HTTP=${res.status}`)
    res = await admin.work('/nodes/register/', { method: 'POST', body: {}, headers: { Origin: 'http://evil.example' } })
    check('错误 Origin 被拒', !isOk(res.body), `HTTP=${res.status}`)
    for (const [i, nodeId] of names.entries()) {
      res = await admin.work('/nodes/register/', { method: 'POST', body: {
        node_id: nodeId, name: nodeId, ip_address: `10.241.${Math.floor(Math.random() * 200) + 20}.${i + 1}`,
        port: 60000 + Math.floor(Math.random() * 4000), permission_level: 'L2', domain_id: `demo-api-${seed}`
      } })
      const created = requireOk(res, '演示建节点')
      if (created.node_id !== nodeId || created.is_duplicate) throw new Error('创建响应指向既有节点，不将其纳入清理')
      createdNodes.push(nodeId)
      check('演示建节点不返回激活凭证', !res.body.data.activation_code)
      check('演示建节点没有生成/消费凭证或绑定设备',
        sqlScalar(`SELECT CONCAT_WS('|',IFNULL(activation_code_hash,''),IFNULL(key_device_id,'')) FROM ${table} WHERE node_id='${nodeId}'`) === '|')
    }
    for (const [label, session, nodeId] of [['A', a, names[0]], ['B', b, names[1]]]) {
      requireOk(await session.switch('/entry', { nodeId }), 'nodeId 入口')
      check(`${label} 直入待初始化节点，无激活`, session.context.principalType === 'NODE' && session.context.nodeId === nodeId)
      const lease = requireOk(await session.work('/node-self/demo-init/lease/', { method: 'POST' }), '初始化租约')
      session.keys = {}
      for (const algorithm of ['SM2', 'SSCL', 'KYBER', 'FALCON']) {
        const material = await cryptoProvider.generate(algorithm, { nodeId, ...(algorithm === 'KYBER' ? { variant: 768 } : {}) })
        session.keys[algorithm] = material
        requireOk(await session.work('/node-self/keys/', { method: 'POST',
          headers: { 'X-Kms-Demo-Init-Lease': lease.leaseId }, body: {
            algorithm, publicKey: material.publicKey, keyId: material.keyId, keyVersion: material.version,
            ...(algorithm === 'KYBER' ? { securityLevel: '768' } : {})
          } }), `登记 ${algorithm}`)
      }
      requireOk(await session.work('/node-self/init/', { method: 'POST', headers: { 'X-Kms-Demo-Init-Lease': lease.leaseId } }), '初始化收尾')
      requireOk(await session.work('/node-self/demo-init/release/', { method: 'POST', body: { leaseId: lease.leaseId } }), '释放初始化租约')
      const before = requireOk(await session.work('/node-self/keys/'), '初始化密钥列表')
      requireOk(await session.switch('/entry', { nodeId }), '同一链接再次进入')
      const after = requireOk(await session.work('/node-self/keys/'), '再次密钥列表')
      check(`${label} 再次进入不生成新版本`, JSON.stringify(before.keys) === JSON.stringify(after.keys) && after.keys.length === 4)
    }
    res = await a.work('/admin/node-authorization-requests/')
    check('节点上下文不能审批', !isOk(res.body), `HTTP=${res.status}`)
    res = await a.work(`/node-self/peers/${names[1]}/keys/`)
    check('批准前仍被唯一授权判据拒绝', res.body?.data?.error_code === 'NOT_AUTHORIZED')
    const requested = requireOk(await a.work('/node-self/authorization-requests/', {
      method: 'POST', body: { targetNodeId: names[1], reason: 'Demo API 闭环' }
    }), '授权申请')
    const requests = requireOk(await a.work('/node-self/authorization-requests/'), '申请列表')
    const pending = (requests.outgoing || []).find(x => x.status === 'pending' && x.id === requested.request?.id)
    if (!pending) throw new Error(`申请单未找到: ${JSON.stringify(requested)}`)
    const nodeRevision = a.context.revision
    requireOk(await a.switch('/admin'), '切换管理员')
    const adminRevision = a.context.revision
    res = await a.work(`/admin/node-authorization-requests/${pending.id}/decide/`, {
      method: 'POST', body: { decision: 'approve', remark: 'Demo API 同服务审批', bidirectional: true }
    })
    requireOk(res, '批准申请')
    check('审批写入原授权表并以 DEMO_ADMIN 留痕',
      Number(sqlScalar(`SELECT COUNT(*) FROM falcon_kds.dvadmin_pqkds_user_node_authorizations WHERE user_id=(SELECT sys_user_id FROM ${table} WHERE node_id='${names[0]}') AND node_id=(SELECT id FROM ${table} WHERE node_id='${names[1]}') AND status='active' AND granted_by LIKE '%DEMO_ADMIN%'`)) === 1)
    requireOk(await a.switch('/node'), '返回节点')
    check('返回原 A 且角色/版本已降级', a.context.nodeId === names[0] && a.context.principalType === 'NODE' && a.context.revision > adminRevision && adminRevision > nodeRevision)
    res = await a.work('/admin/node-authorization-requests/', { headers: { 'X-Kms-Demo-Revision': String(adminRevision) } })
    check('旧管理员上下文不能继续管理', !isOk(res.body))
    res = await a.work(`/node-self/peers/${names[1]}/keys/`)
    check('批准后原授权判据真实放行', isOk(res.body))

    const { buildNodeEnvelope, generatePayloadKey, newBatchId, signNodeEnvelope } = await import('../kms-updatedel/front/src/utils/crypto/envelope-signing.js')
    const { verifyNodeEnvelope, unwrapNodeEnvelope, nodeProof } = await import('../kms-updatedel/front/src/utils/crypto/node-envelope.js')
    const payloadKey = generatePayloadKey(), batchId = newBatchId(), expiresAt = new Date(Date.now() + 3600000).toISOString()
    const built = await buildNodeEnvelope({ provider: cryptoProvider, payloadKey, wrapping: 'KYBER',
      recipientPublicKeyHex: b.keys.KYBER.publicKey, batchId, senderNodeId: names[0], receiverNodeId: names[1],
      recipientKeyId: b.keys.KYBER.keyId, recipientKeyVersion: 1, expiresAt })
    const signature = await signNodeEnvelope(cryptoProvider, a.keys.FALCON.keyRef, built.envelope)
    const distributionBody = {
      receiverNodeId: names[1], protectionAlgorithm: 'KYBER', recipientKeyId: b.keys.KYBER.keyId,
      recipientKeyVersion: 1, falconKeyId: a.keys.FALCON.keyId, falconKeyVersion: 1,
      batchId, expiresAt, envelope: built.envelope, signature, keyHash: built.keyHash
    }
    requireOk(await admin.work(`/nodes/${names[0]}/`, { method: 'PATCH', body: { permission_level: 'L1' } }), '降低本轮节点能力等级')
    res = await a.work('/node-self/distributions/', { method: 'POST', body: distributionBody })
    check('已有对端授权也不能绕过 L1 能力等级', !isOk(res.body) && res.body?.data?.error_code === 'NOT_AUTHORIZED')
    requireOk(await admin.work(`/nodes/${names[0]}/`, { method: 'PATCH', body: { permission_level: 'L2' } }), '恢复本轮节点能力等级')
    const delivery = requireOk(await a.work('/node-self/distributions/', {
      method: 'POST', body: distributionBody
    }), 'Demo 节点签名分发')
    check('Demo 真实 Falcon 验签成功', delivery.signatureVerified === true)
    const sid = delivery.sessionId
    if (!sid) throw new Error('分发没有会话 ID')
    const envs = requireOk(await b.work('/node-self/envelopes/'), '取信封')
    const entry = envs.items.find(x => x.sessionId === sid)
    if (!entry) throw new Error('接收节点未找到信封')
    const verified = await verifyNodeEnvelope({ provider: cryptoProvider, envelope: entry.envelope,
      signatureB64: entry.envelope.signature, senderFalconPublicKeyHex: a.keys.FALCON.publicKey })
    check('接收方在本机验签通过', verified.ok === true)
    const recovered = await unwrapNodeEnvelope({ provider: cryptoProvider, keyRef: b.keys.KYBER.keyRef, envelope: entry.envelope })
    check('Demo 接收方解出的 SM4 与发送方逐字节一致', Buffer.from(recovered).equals(Buffer.from(payloadKey)))
    requireOk(await b.work(`/node-self/envelopes/${entry.envelopeId}/verify/`, { method: 'POST' }), '服务端复核')
    requireOk(await b.work(`/node-self/envelopes/${entry.envelopeId}/recover/`, { method: 'POST' }), '解封回执')
    for (const [session, key] of [[a, payloadKey], [b, recovered]]) {
      requireOk(await session.work(`/node-self/sessions/${sid}/confirm/`, {
        method: 'POST', body: { proof: await nodeProof({ payloadKey: key, sessionId: sid }) }
      }), '双方确认')
    }
    check('双方证明一致，会话在原表成为 established',
      sqlScalar(`SELECT status FROM falcon_kds.dvadmin_pqkds_session_keys WHERE session_id='${sid}'`) === 'established')
    // 普通分发信封在本表记 node1=接收方、node2=NULL；预分配项才记发送/接收
    // 两方。按真实归属判，不能让测试假定“每种资源都是双向节点对”。
    const poolList = requireOk(await b.work('/key-pool/'), '演示接收节点池项列表')
    const ownPoolRows = Array.isArray(poolList) ? poolList : (poolList.results || poolList.data || [])
    check('演示节点可以读参与的池项且不会枚举其他节点资源', ownPoolRows.length > 0 && ownPoolRows.every(row => row.node1_id === names[1] || row.node2_id === names[1]))
    const poolStats = requireOk(await b.work('/key-pool/stats/'), '演示接收节点池统计')
    check('池统计按可信节点归属过滤', poolStats.total === ownPoolRows.length)
    const senderStats = requireOk(await a.work('/key-pool/stats/'), '发送方不会读到接收方的信封资源统计')
    check('只给接收方的信封不会泄漏到发送方池统计', senderStats.total === 0)
    const normal = await fetch('http://127.0.0.1/pqkds-api/admin/node-authorization-requests/', { headers: { Cookie: admin.cookie } })
    const normalBody = await normal.json().catch(() => null)
    check('Demo Cookie 不赋予原 Standalone API 权限', !isOk(normalBody))
    for (const path of ['/demo', '/updatedel/demo', '/demo-api/lifecycle/demo/context']) {
      const r = await fetch(`http://127.0.0.1${path}`, { redirect: 'manual' })
      check(`旧80网关不开放 ${path}`, r.status === 404)
    }
    const bad = new DemoSession()
    res = await bad.switch('/entry', { nodeId: '../bad' })
    check('非法 nodeId 被拒', !isOk(res.body))
    res = await new DemoSession().switch('/entry', { nodeId: `Missing-${seed}` })
    check('不存在节点不自动创建', !isOk(res.body) && Number(sqlScalar(`SELECT COUNT(*) FROM ${table} WHERE node_id='Missing-${seed}'`)) === 0)
    const authRows = requireOk(await admin.work('/admin/node-authorizations/'), '授权列表')
    const grantRow = authRows.items.find(x => x.nodeCode === names[1] && x.userId === Number(sqlScalar(`SELECT sys_user_id FROM ${table} WHERE node_id='${names[0]}'`)))
    if (!grantRow) throw new Error('授权记录缺失')
    requireOk(await admin.work(`/admin/node-authorizations/${grantRow.id}/revoke/`, { method: 'POST' }), '撤销授权')
    res = await a.work(`/node-self/peers/${names[1]}/keys/`)
    check('撤销后立即拒绝原节点继续分发', res.body?.data?.error_code === 'NOT_AUTHORIZED')
  } catch (error) {
    check('双模式 API 闭环执行', false, error.stack)
  } finally {
    // 只通过受保护的业务删除 API 清理刚确认创建的随机节点，不在容器内执行
    // ORM/SQL 写脚本；管理员闸门、审计和关联清理与界面操作完全相同。
    for (const nodeId of createdNodes) {
      try {
        const cleanup = await admin.work(`/nodes/${encodeURIComponent(nodeId)}/`, { method: 'DELETE' })
        check(`清理本轮节点 ${nodeId}`, isOk(cleanup.body), `code=${cleanup.body?.code}`)
      } catch (error) { check('清理本轮测试夹具', false, error.message) }
    }
    finish()
  }
}
