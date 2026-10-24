import { securityRequestGroups, parseCostFields } from './evidence-presentation.js'
import { quantumModels, costFieldNames } from '../config/quantumModels.js'

const number = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '未记录'
const verdict = value => value === true ? 'success' : value === false ? 'failed' : 'unknown'
const check = value => value === true ? '通过' : value === false ? '未通过' : '未记录'
const event = (id, from, to, action, output, fields, extra = {}) => ({ id, from, to, action, output, fields, ...extra })

// Only recorded observations become events. Durations refer to the named
// operation, never an inferred share of the overall request time.
export function securityExecution(run) {
  const e = run?.quantumEvidence
  if (e) {
    const rpc = (run.requests || []).find(row => row.url === '/evaluate')
    const rows = []
    if (rpc) rows.push(event('evaluator', '验收后端', '量子评估器', 'POST /evaluate', `返回 ${e.estimates?.length ?? 0} 组参数评估`, [
      ['模型', quantumModels[e.model]?.method || e.model], ['响应', `HTTP ${rpc.statusCode}`], ['记录时间', rpc.recordedAt]
    ], { durationMs: rpc.durationMs, at: rpc.recordedAt, state: rpc.statusCode === 200 ? 'success' : 'failed' }))
    for (const row of e.estimates || []) {
      const costs = parseCostFields(row.rawCost)
      rows.push(event(`estimate-${row.variant}`, '量子评估器', quantumModels[e.model]?.method || e.model,
      `评估 Kyber-${row.variant}`, `β=${row.beta} · 运算量 2^${number(row.log2Rop)} rop`, [
        ['公开参数', `n=${row.n}, q=${row.q}, m=${row.m}`], ['秘密分布', row.secretDistribution], ['误差分布', row.errorDistribution],
        ...((quantumModels[e.model]?.fields || []).filter(key => costs[key] !== undefined).map(key => [costFieldNames[key] || key, costs[key]])),
        ['成本模型', e.costModel]
      ], { durationMs: row.durationMs, state: Number.isFinite(row.log2Rop) && row.log2Rop > 0 ? 'success' : 'unknown' }))
    }
    return rows
  }
  if (run?.caseId?.startsWith('quantum-lwe-')) return []
  const groups = securityRequestGroups(run), rows = (run?.probeSteps || []).map((step, index) => event(`probe-${index}`, '攻击执行器', step.kind,
    step.name, step.detail, [], { at: step.recordedAt, state: step.state, kind: step.kind }))
  for (const [index, row] of groups.core.entries()) rows.push(event(`attack-${index}`, '攻击执行器', run.validationRule || '业务接口防御', row.name,
    `${run.reasonMatched === true ? '按预期拒绝' : run.actualReason ? '拒绝原因未匹配' : '未取得拒绝证据'} · ${responseSummary(row)} · ${run.actualReason || row.message || '未记录原因'}`, [
      ['请求', `${row.method} ${row.url}`], ['传输状态', `HTTP ${row.statusCode || '无响应'}`], ['业务状态', businessSummary(row)], ['攻击输入', run.testInput], ['校验机制', run.validationRule],
      ['预期拒绝', run.expectedReason], ['预期错误码', run.expectedCode !== run.expectedReason ? run.expectedCode : undefined],
      ['实际拒绝', run.actualReason || row.message], ['实际错误码', run.actualCode !== run.actualReason ? run.actualCode : undefined]
    ], { at: row.recordedAt, durationMs: row.durationMs, state: run.status === 'running' && !run.actualReason ? 'unknown' : verdict(run.reasonMatched) }))
  const after = groups.controls.findLast(row => /攻击后|复查合法/.test(row.name || ''))
  if (after && !(run.probeSteps || []).some(step => step.kind === 'CONTROL' && step.name === '攻击后合法节点读取')) rows.push(event('legal-control', '合法节点', '节点资料接口', '攻击后执行合法业务',
    `HTTP ${after.statusCode} · ${run.status === 'running' && !run.legalControlPassed ? '核验中' : check(run.legalControlPassed)}`, [['请求', `${after.method} ${after.url}`], ['实际响应', after.message]],
    { at: after.recordedAt, durationMs: after.durationMs, state: run.status === 'running' && !run.legalControlPassed ? 'unknown' : verdict(run.legalControlPassed) }))
  return rows.sort((a, b) => {
    if (!a.at || !b.at) return 0
    // Retain sub-millisecond order from the executor's RFC3339Nano timestamps.
    return Date.parse(a.at) - Date.parse(b.at) || (a.at < b.at ? -1 : a.at > b.at ? 1 : 0)
  })
}

function businessCode(row) {
  const match = String(row?.message || '').match(/businessCode=([0-9]+)/)
  return match ? Number(match[1]) : null
}

function businessSummary(row) {
  const code = businessCode(row)
  if (code === null) return '未记录'
  return code === 200 ? '业务成功（200）' : `业务拒绝（${code}）`
}

function responseSummary(row) {
  const status = row?.statusCode || '无响应'
  const code = businessCode(row)
  if (code !== null && code !== 200) return `HTTP ${status} · 业务拒绝 ${code}`
  if (Number(status) >= 400) return `HTTP ${status} · 传输层拒绝`
  return `HTTP ${status} · 业务成功`
}

export function performanceExecution(run) {
  if (!run) return []
  const g = run.generationEvidence
  if (g) return [
    event('inputs', '验收执行器', 'SSCL生成接口', '逐一提交独立用户公钥', `独立输入 ${number(g.selected)} · 提交 ${number(g.submitted)}`, [['HTTP成功', number(g.httpSuccess)], ['业务受理', number(g.accepted)]], { at: g.startedAt, durationMs: g.submissionMs, state: g.accepted === g.selected ? 'success' : 'failed' }),
    event('registration', '登记核验器', '密钥数据库', '核验本批登记及材料摘要', `登记 ${number(g.registered)} · 去重有效 ${number(g.completed)}`, [['重复', number(g.duplicates)], ['无效登记', number(g.invalid)], ['未完成', number(g.failed)], ['端到端耗时', `${number(g.elapsedMs)} ms`]], { at: g.observedAt, state: g.verified && g.completed === g.selected ? 'success' : 'failed' })
  ]
  const e = run.fixedUpdateEvidence, a = run.abnormalEvidence, s = run.symmetricEvidence
  if (e) return [
    event('select', '验收执行器', '密钥记录', '选取独立 SM2 密钥', `${number(e.selected)} 把`, [['来源生成批次', e.sourceRunId || '未附批次编号']], { state: e.selected > 0 ? 'success' : 'unknown' }),
    event('submit', '并发执行器', '密钥更新接口', '逐钥提交更新', `提交 ${number(e.submitted)} · 受理 ${number(e.accepted)}`, [
      ['重复响应', number(e.duplicates)], ['请求失败', number(e.rejected)], ['受理吞吐', `${number(e.acceptedTps)} TPS`]
    ], { durationMs: e.submissionMs, at: e.startedAt, state: e.rejected > 0 ? 'failed' : e.submitted > 0 ? 'success' : 'unknown' }),
    event('verify', '验收核验器', '密钥数据库', '核验版本与材料变更', `${number(e.completed)} 把完成更新 · ${check(e.verified)}`, [
      ['核验依据', '版本递增、密钥材料改变及数据库记录'], ['从首次提交至核验', `${number(e.elapsedMs)} ms`], ['异步上链', '不计入本次等待范围']
    ], { state: verdict(e.verified) })
  ]
  if (a) return [
    event('inject', '隔离样本构造器', '测试数据库', '注入异常密钥与正常对照', `${number(a.injected)} 异常 · ${number(a.controls)} 对照`, [
      ['批次', a.batchId], ...((a.rules || []).map(row => [row.rule, `注入 ${number(row.injected)}，检测 ${number(row.detected)}，回收 ${number(row.revoked)}`]))
    ], { at: a.beforeAt, state: a.injected > 0 ? 'success' : 'unknown' }),
    event('detect', '异常扫描服务', '密钥数据库', '扫描并识别异常密钥', `识别 ${number(a.detected)} 条`, [
      ['识别耗时', `${number(a.detectionElapsedMs)} ms`], ['识别时间', a.detectionAt || '未记录'], ['异常规则', (a.rules || []).map(row => row.rule).join('、')]
    ], { durationMs: a.detectionElapsedMs, at: a.detectionAt, state: a.detected === a.injected ? 'success' : 'failed' }),
    event('revoke', '自动回收服务', '密钥数据库', '自动发起回收并更新状态', `发起 ${number(a.attempted)} · 回收 ${number(a.revoked)}`, [
      ['自动回收', a.autoRevoked === true ? '已执行' : '未确认'], ['开始时间', a.revokeStartedAt || '未记录'], ['实际失败', number(a.attempted - a.revoked)], ['未发起', number(a.injected - a.attempted)], ['实际批次数', number(a.batches?.length)], ['回收耗时', `${number(a.elapsedMs)} ms`]
    ], { at: a.revokeStartedAt, state: a.autoRevoked === true && a.revoked === a.attempted ? 'success' : 'failed' }),
    event('invalidate', '回收服务', '预分配池 / 会话', '关联业务失效与对照核验', `池项 ${number(a.poolRevoked)} · 会话 ${number(a.sessionsRevoked)} 失效`, [
      ['正常对照通过', `${number(a.controlsPassed)} / ${number(a.controls)}`], ['隔离样本清理', check(a.cleanupComplete)]
    ], { at: a.observedAt, state: Number.isFinite(a.controls) ? verdict(a.controlsPassed === a.controls && a.cleanupComplete === true) : 'unknown' })
  ]
  if (s) return [
    event('prepare', '隔离样本构造器', 'SM4 预分配池', '准备到期保护包', `${number(s.injected)} 到期 · ${number(s.controls)} 对照`, [
      ['批次', s.batchId], ['保护材料有效性', check(s.materialVerified)]
    ], { at: s.beforeAt, state: verdict(s.materialVerified) }),
    event('delete', '到期回收服务', '预分配池数据库', '筛选、删除并提交事务', `实际回收 ${number(s.reclaimed)} · 剩余 ${number(s.remaining)}`, [
      ['对象', '到期 SM4 对称会话密钥保护包'], ['计时范围', '数据库筛选、删除与事务提交']
    ], { durationMs: s.elapsedMs, state: Number.isFinite(s.remaining) ? verdict(s.remaining === 0 && s.reclaimed === s.injected) : 'unknown' }),
    event('controls', '验收核验器', '正常对照记录', '核验保留记录与清理', `${number(s.controlsPassed)} / ${number(s.controls)} 对照通过`, [
      ['隔离样本清理', check(s.cleanupComplete)], ['含样本准备总耗时', `${number(s.totalMs)} ms`]
    ], { at: s.observedAt, state: Number.isFinite(s.controls) ? verdict(s.controlsPassed === s.controls && s.cleanupComplete === true) : 'unknown' })
  ]
  if (run.scenarioId === 'generate-tps' && !['preparing', 'running', 'queued', 'cancelling'].includes(run.status) && run.summary?.totalRequests !== undefined) return [event('http', 'wrk 并发执行器', '密钥生成接口', '执行 HTTP 负载测试',
    `完成 ${number(run.summary.totalRequests)} · 非成功响应 ${number(run.summary.non2xxResponses)}`, [
      ['连接错误', number(run.summary.socketErrors)], ['平均延迟', `${number(run.summary.avgLatencyMs)} ms`],
      ['观测范围', '本轮接口成功响应统计']
    ], { state: 'unknown' })]
  return []
}

export function latticeExecution(result) {
  if (!result) return []
  const p = result.preparation || {}, matrix = `${p.n ?? '?'} × ${p.dimension ?? '?'}，q=${p.q ?? '?'}`
  const publicFields = [['材料编号', p.id], ['公共矩阵', matrix], ['公共参数摘要', p.publicDigest]]
  if (result.caseId === 'offline-trapdoor') return [
    event('trapgen', '格参数服务', 'TrapGen', '构造公共矩阵与陷门格基', `核格关系 ${check(result.kernelRelation)} · 满秩 ${check(result.fullRank)}`, [
      ...publicFields, ['行列式指数 log_q |det(T)|', number(result.determinantLogQ)], ['最大 Gram-Schmidt 长度', number(result.maxGramSchmidt)]
    ], { durationMs: result.generationMs, state: verdict(result.kernelRelation && result.fullRank) }),
    event('persist', '格参数服务', '加密材料库', '加密保存后重新加载验证', check(result.secretPersistedEncrypted), [['材料编号', p.id], ['验证依据', '重载后的格基关系及完整性校验']], { state: verdict(result.secretPersistedEncrypted) })
  ]
  if (result.caseId === 'basis-delegation') return [
    event('delegate', '格参数服务', 'ExtBasis 委派计算', '以主参数和节点派生委派材料', `节点绑定 ${check(result.nodeBound)} · 格关系 ${check(result.kernelRelation)}`, [
      ...publicFields, ['主材料编号', p.parentId], ['绑定节点', `${p.nodeName || ''} ${p.nodeId || ''}`], ['持久化材料', result.reused ? '复用已有记录' : '新建记录']
    ], { durationMs: result.delegationMs, state: verdict(result.nodeBound && result.kernelRelation) }),
    event('preimage', '持久化委派材料', 'SamplePre / Verify', '采样短原像并核验', check(result.preimageVerified), [['验证依据', '模关系与向量长度约束']], { state: verdict(result.preimageVerified) })
  ]
  const processMode = result.executionMode === 'process', unit = processMode ? '进程' : '线程'
  return [
    event('sample', '保护包预分配服务', `并行采样${unit}池`, '为保护包生成短向量证明', `有效 ${number(result.valid)} / ${number(result.count)} · 实际 ${number(result.usedWorkers)} ${unit}`, [
      ...publicFields, [`配置${unit}数`, number(result.workers)], ['峰值在途任务', number(result.peakInFlight)],
      ...(processMode ? [['进程池', result.poolReused ? '复用已有进程及格基' : '新建进程并加载格基'],
        ['执行器准备耗时', `${number(result.poolSetupMs)} ms`], ['排队耗时', `${number(result.queueMs)} ms`],
        ['计算及进程通信耗时', `${number(result.computeMs)} ms`], ['计时范围', '采样耗时包含排队、执行器准备、计算和进程通信']] : [])
    ], { durationMs: result.samplingMs, state: Number.isFinite(result.count) ? verdict(result.valid === result.count) : 'unknown' }),
    ...((result.checks || []).filter(row => !/清理/.test(row.name)).map((row, index) => event(`check-${index}`, '预分配流程', '关系与业务校验', row.name, String(row.actual), [['预期', row.expected]], { state: verdict(row.passed) }))),
    event('cleanup', '隔离测试事务', '预分配池', '回滚隔离批次', check(result.cleanupComplete), [['批次', result.poolId]], { state: verdict(result.cleanupComplete) })
  ]
}

export function workerTimeline(spans) {
  const valid = (spans || []).filter(row => row.worker && Number.isFinite(row.startMs) && Number.isFinite(row.endMs) && row.startMs >= 0 && row.endMs >= row.startMs)
  const durationMs = Math.max(0, ...valid.map(row => row.endMs))
  if (!durationMs) return { durationMs: 0, rows: [] }
  const workers = [...new Set(valid.map(row => row.worker))].sort()
  return { durationMs, rows: workers.map(worker => ({ worker, spans: valid.filter(row => row.worker === worker).sort((a, b) => a.startMs - b.startMs).map(row => ({ ...row, left: row.startMs * 100 / durationMs, width: (row.endMs - row.startMs) * 100 / durationMs })) })) }
}

export function preallocationExecution(e) {
  if (!e) return []
  const rows = []
  if (Number.isFinite(e.generated)) rows.push(event('local', '发送节点本机', 'SM4 / Kyber / Falcon', '生成、封装并签名保护包',
    `生成 ${number(e.generated)} · 失败 ${number(e.failed)}`, [['请求数量', number(e.requested)], ['本机吞吐', `${number(e.localThroughput)} 条/秒`]],
    { durationMs: e.localMs, state: e.failed === 0 ? 'success' : e.failed > 0 ? 'failed' : 'unknown' }))
  if (Number.isFinite(e.serverMs)) rows.push(event('pool', '发送节点', '预分配池服务', '上传保护包并处理入池',
    `服务端吞吐 ${number(e.serverThroughput)} 条/秒`, [['执行证据', e.evidence]], { durationMs: e.serverMs, state: e.verified === true ? verdict(e.passed) : 'unknown' }))
  return rows
}
