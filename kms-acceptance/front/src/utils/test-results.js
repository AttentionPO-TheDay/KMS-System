export const isActiveRun = run => ['preparing', 'running', 'queued', 'cancelling'].includes(run?.status)

export const algorithmCheckIds = {
  'pq-parameter-downgrade': [512, 768, 1024].flatMap(v => [`${v}-roundtrip`, `${v}-interop`, `${v}-tamper`]),
  'pq-secret-upload': [512, 768, 1024].flatMap(v => [`${v}-roundtrip`, `${v}-other-control`, `${v}-wrong-key`]),
  'pq-sign-encrypt-confusion': ['falcon-roundtrip', 'falcon-interop', 'falcon-message-tamper'],
  'pq-issuance-source-forgery': ['falcon-roundtrip', 'falcon-interop', 'falcon-signature-tamper', 'falcon-other-control', 'falcon-wrong-key']
}
export function algorithmPassed(run) {
  const ids = algorithmCheckIds[run?.caseId], evidence = run?.algorithmEvidence
  return Boolean(ids && run.evidenceVersion === 3 && run.protocolPassed === true && evidence?.version === 1 &&
    evidence.caseId === run.caseId && evidence.passed === true && evidence.source && evidence.scope &&
    evidence.checks?.length === ids.length && evidence.checks.every((check, i) =>
      check.id === ids[i] && check.passed === true && check.status === 'passed' && check.expected && check.actual && check.recordedAt))
}

export function securityOutcome(run) {
  if (!run) return { state: 'pending', label: '待测试' }
  if (isActiveRun(run)) return { state: 'running', label: run.status === 'cancelling' ? '正在停止' : '执行中' }
  if (run.caseId?.startsWith('quantum-lwe-')) return quantumEvaluated(run)
    ? { state: 'evaluated', label: '仿真与评估完成' }
    : { state: 'incomplete', label: run.status === 'cancelled' ? '已停止' : '仿真未完成' }
  if (run.status === 'completed' && run.verdict === 'blocked' && run.passed === true &&
      [2, 3].includes(run.evidenceVersion) && run.reasonMatched === true && run.legalControlPassed === true &&
      run.expectedCode && run.expectedCode === run.actualCode && run.expectedReason && run.expectedReason === run.actualReason) {
    if (run.caseId?.startsWith('pq-')) return algorithmPassed(run)
      ? { state: 'passed', label: '算法与协议验证通过' }
      : { state: 'incomplete', label: '协议通过，算法待验' }
    return { state: 'passed', label: '防御成功' }
  }
  if (run.status === 'completed' && run.verdict === 'vulnerable') return { state: 'failed', label: '防御校验未通过' }
  return { state: 'incomplete', label: run.status === 'cancelled' ? '已停止' : '测试未完成' }
}

export function quantumEvaluated(run) {
  const models = { 'quantum-lwe-usvp': 'primal_usvp', 'quantum-lwe-bdd': 'primal_bdd', 'quantum-lwe-dual': 'dual' }
  const e = run?.quantumEvidence, c = e?.circuit
  return Boolean(models[run?.caseId] && run.status === 'completed' && run.verdict === 'evaluated' && run.passed === false &&
    run.evidenceVersion === 4 && run.legalControlPassed === true && e?.version === 1 && e.caseId === run.caseId &&
    e.model === models[run.caseId] && e.evaluationComplete === true && e.acceptancePassed === false &&
    e.estimatorCommit === 'e4333d9bf9ef42fd8a29651b0c559fba7ce0d834' && e.recordedAt && e.scope &&
    c?.verified === true && c.qubits === 8 && c.searchSpace === 256 && c.shots === 256 &&
    c.target?.length === 8 && c.recovered === c.target && c.successProbability >= .99 && c.successProbability <= 1 &&
    Math.abs(c.norm - 1) < 1e-9 && Math.abs(c.baselineProbability - 1 / 256) < 1e-9 &&
    e.estimates?.length === 3 && e.estimates.every((r, i) => r.variant === [512, 768, 1024][i] &&
      r.n === r.variant && r.m === r.variant && r.q === 3329 && Number.isFinite(r.log2Rop) && r.log2Rop > 0 && r.beta >= 2))
}

export function securityProgress(caseIds, latest, target) {
  if (caseIds.length && caseIds.every(id => id.startsWith('quantum-lwe-'))) {
    const outcomes = caseIds.map(id => securityOutcome(latest.get(id)))
    const evaluatedCount = outcomes.filter(o => o.state === 'evaluated').length
    const runningCount = outcomes.filter(o => o.state === 'running').length
    const incompleteCount = outcomes.filter(o => o.state === 'incomplete').length
    const pendingCount = outcomes.filter(o => o.state === 'pending').length
    const state = runningCount ? 'running' : incompleteCount ? 'incomplete' : evaluatedCount === caseIds.length ? 'evaluated' : evaluatedCount ? 'partial' : 'pending'
    return { state, statusLabel: state === 'running' ? '执行中' : state === 'evaluated' ? '仿真与评估完成' : state === 'incomplete' ? '仿真未完成' : `已评估 ${evaluatedCount}/${caseIds.length} 项`,
      evaluatedCount, passedCount: 0, pendingCount, runningCount, failedCount: 0, incompleteCount, thresholdMet: false,
      note: '弱参数电路为正向对照；生产参数结果为成本估计，需确认任务书验收口径。' }
  }
  const outcomes = caseIds.map(id => securityOutcome(latest.get(id)))
  const count = state => outcomes.filter(item => item.state === state).length
  const passedCount = count('passed'), pendingCount = count('pending')
  const runningCount = count('running'), failedCount = count('failed'), incompleteCount = count('incomplete')
  const quantum = caseIds.length > 0 && caseIds.every(id => id.startsWith('pq-'))
  const thresholdMet = passedCount >= target
  let state = 'pending', statusLabel = '待测试'
  if (runningCount) { state = 'running'; statusLabel = '执行中' }
  else if (failedCount) { state = 'failed'; statusLabel = '存在未通过项' }
  else if (incompleteCount) { state = 'incomplete'; statusLabel = quantum && outcomes.every(o => o.label === '协议通过，算法待验') ? '协议通过，算法待验' : '有测试未完成' }
  else if (caseIds.length && passedCount === caseIds.length && thresholdMet) { state = 'passed'; statusLabel = quantum ? '全部验证通过' : '全部防御成功' }
  else if (passedCount) { state = 'partial'; statusLabel = `已通过 ${passedCount}/${caseIds.length} 项` }
  const note = state === 'passed' ? quantum ? `${passedCount} 类算法负向场景、正常对照、互操作和协议断言均通过。` : `${passedCount} 项场景的拒绝断言通过，合法节点读取正常。`
    : pendingCount ? `还有 ${pendingCount} 项待测试；验收下限为 ${target} 类。` : ''
  return { state, statusLabel, passedCount, pendingCount, runningCount, failedCount, incompleteCount, thresholdMet, note }
}

export function performanceOutcome(run) {
  if (!run) return { state: 'pending', label: '待执行' }
  if (isActiveRun(run)) return { state: 'running', label: '执行中' }
  if (run.scenarioId === 'symmetric-reclaim-tps' && !validSymmetricRun(run)) return { state: 'incomplete', label: '缺少对称密钥回收核验，需重测' }
  if (run.scenarioId === 'update-tps' && !run.error && (run.fixedUpdateEvidence?.version !== 2 || run.fixedUpdateEvidence?.verified !== true)) return { state: 'incomplete', label: '缺少密钥材料更新核验，需重测' }
  if (['revoke-tps', 'revoke-rate'].includes(run.scenarioId) && run.abnormalEvidence?.version !== 2) return { state: 'incomplete', label: '缺少异常样本证据，需重测' }
  const needsFinalState = run.scenarioId === 'revoke-rate' || run.metricCheck?.enforced === true
  if (run.status === 'passed' && run.passedTps === true && (!needsFinalState || (run.metricCheck?.collected === true && run.metricCheck?.passed === true))) return { state: 'passed', label: '已通过' }
  if (['failed', 'failed_threshold'].includes(run.status) && !run.error && Number(run.summary?.totalRequests) > 0) return { state: 'failed', label: '未达到指标' }
  return { state: 'incomplete', label: run.status === 'cancelled' ? '已停止' : '测试未完成' }
}

export function measuredPerformance(run, criterion) {
  if (!run || isActiveRun(run)) return null
  if (run.scenarioId === 'symmetric-reclaim-tps' && !validSymmetricRun(run)) return null
  if (run.scenarioId === 'update-tps' && (run.fixedUpdateEvidence?.version !== 2 || run.fixedUpdateEvidence?.verified !== true)) return null
  if (['revoke-tps', 'revoke-rate'].includes(run.scenarioId) && run.abnormalEvidence?.version !== 2) return null
  if (criterion?.id === 'revoke-rate' || run.scenarioId === 'revoke-rate') {
    return run.metricCheck?.collected === true ? run.metricCheck.value : null
  }
  return Number(run.summary?.totalRequests) > 0 ? run.summary.successfulRequestsPerSec : null
}

function validSymmetricRun(run) {
  const e = run.symmetricEvidence, check = run.metricCheck
  return e?.version === 1 && e.source === 'sm4-expired-pool-isolated-mysql' && e.isolated === true &&
    e.cleanupComplete === true && e.materialVerified === true && e.injected === 12000 && e.controls === 4 &&
    Number.isFinite(e.elapsedMs) && e.elapsedMs > 0 && check?.enforced === true && check.collected === true &&
    check.kind === 'symmetric_reclamation_closure'
}
