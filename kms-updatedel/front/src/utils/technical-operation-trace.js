// Public identifiers only. Never pass payloads, key material or whole API replies.
const fields = new Set(['nodeId', 'peerNodeId', 'algorithm', 'keyId', 'version', 'nextVersion',
  'batchId', 'poolId', 'sessionId', 'requested', 'prepared', 'accepted', 'rejected',
  'sessionStatus', 'keyStored', 'expiresAt', 'generated', 'wrapped', 'signed', 'uploaded',
  'remaining', 'selfTestOk', 'reused', 'reconciled'])

const workflows = {
  preallocation: [
    ['peer', '并行抽样短向量', ['peerNodeId', 'keyId', 'version']],
    ['prepare', '离线生成格陷门', ['poolId', 'requested', 'generated', 'wrapped', 'signed']],
    ['submit', '快速委派格基向量', ['poolId', 'uploaded', 'accepted', 'rejected']]
  ],
  distribution: [
    ['prepare', '载荷生成与版本绑定', ['peerNodeId', 'keyId', 'version', 'batchId']],
    ['wrap', '接收方公钥封装', ['algorithm', 'keyId', 'version', 'batchId']],
    ['sign', 'Falcon 信封签名', ['batchId', 'signed']],
    ['submit', '分发登记与会话创建', ['batchId', 'sessionId', 'sessionStatus']],
    ['store', '本机会话材料保存', ['sessionId', 'keyStored']]
  ],
  pool: [
    ['consume', '预分配资源取用', ['batchId', 'keyId', 'version', 'remaining']],
    ['sign', 'Falcon 信封签名', ['batchId', 'signed']],
    ['submit', '信封签名提交', ['batchId', 'sessionId']],
    ['store', '本机会话材料保存', ['sessionId', 'keyStored']]
  ],
  update: [
    ['identity', '节点身份与生产版本校验', ['nodeId', 'keyId', 'version', 'nextVersion']],
    ['material', '本机新版本生成与封存', ['keyId', 'nextVersion', 'reused']],
    ['selftest', '本机材料自检', ['keyId', 'nextVersion', 'selfTestOk']],
    ['register', '公钥登记与版本更新', ['keyId', 'nextVersion']],
    ['refresh', '生产版本与本机公钥对账', ['keyId', 'nextVersion', 'reconciled']]
  ]
}

function publicFacts(values = {}) {
  return Object.fromEntries(Object.entries(values).filter(([key, value]) => fields.has(key) &&
    (typeof value === 'boolean' || typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value))))
    .map(([key, value]) => [key, typeof value === 'string' ? value.slice(0, 160) : value]))
}

export function createTechnicalTrace() {
  return { status: 'idle', startedAt: '', facts: {}, events: [], stages: [], activeStage: '' }
}

export function recordTechnicalTrace(trace, label, values = {}) {
  if (trace.status !== 'running') return
  Object.assign(trace.facts, publicFacts(values))
  trace.events.push({ label, at: new Date().toISOString(), stageId: trace.activeStage, facts: { ...trace.facts } })
  if (trace.events.length > 40) trace.events.shift()
}

export function startTechnicalTrace(trace, values, kind) {
  Object.assign(trace, createTechnicalTrace(), { status: 'running', startedAt: new Date().toISOString() })
  trace.stages = (workflows[kind] || []).map(([id, title, evidence]) => ({
    id, title, evidence, status: 'pending', startedAt: '', finishedAt: '', label: '', facts: {}
  }))
  recordTechnicalTrace(trace, '业务操作开始', values)
}

export function progressTechnicalStage(trace, id, values) {
  const stage = trace.stages.find(item => item.id === id)
  if (trace.status !== 'running' || stage?.status !== 'running') return
  Object.assign(trace.facts, publicFacts(values))
  Object.assign(stage.facts, trace.facts)
}

export function setTechnicalStage(trace, id, status, label, values) {
  const stage = trace.stages.find(item => item.id === id)
  if (trace.status !== 'running' || !stage || !['running', 'success', 'partial', 'failed'].includes(status)) return
  if (!['pending', 'running'].includes(stage.status)) return
  trace.activeStage = id
  stage.startedAt ||= new Date().toISOString()
  stage.status = status
  stage.label = label
  if (status !== 'running') stage.finishedAt = new Date().toISOString()
  recordTechnicalTrace(trace, label, values)
  stage.facts = { ...trace.facts }
}

export function finishTechnicalTrace(trace, status, label, values) {
  if (!['success', 'partial', 'failed'].includes(status)) return
  if (trace.status !== 'running') return
  for (const stage of trace.stages.filter(item => item.status === 'running')) {
    setTechnicalStage(trace, stage.id, status === 'failed' ? 'failed' : 'partial', label, values)
  }
  if (status === 'success' && trace.stages.some(stage => stage.status !== 'success')) status = 'partial'
  recordTechnicalTrace(trace, label, values)
  trace.status = status
}
