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

export function securityProgress(caseIds, latest, target) {
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
  if (run.scenarioId === 'update-tps' && !run.error && (run.fixedUpdateEvidence?.version !== 2 || run.fixedUpdateEvidence?.verified !== true)) return { state: 'incomplete', label: '缺少密钥材料更新核验，需重测' }
  if (['revoke-tps', 'revoke-rate'].includes(run.scenarioId) && run.abnormalEvidence?.version !== 2) return { state: 'incomplete', label: '缺少异常样本证据，需重测' }
  const needsFinalState = run.scenarioId === 'revoke-rate' || run.metricCheck?.enforced === true
  if (run.status === 'passed' && run.passedTps === true && (!needsFinalState || (run.metricCheck?.collected === true && run.metricCheck?.passed === true))) return { state: 'passed', label: '已通过' }
  if (['failed', 'failed_threshold'].includes(run.status) && !run.error && Number(run.summary?.totalRequests) > 0) return { state: 'failed', label: '未达到指标' }
  return { state: 'incomplete', label: run.status === 'cancelled' ? '已停止' : '测试未完成' }
}

export function measuredPerformance(run, criterion) {
  if (!run || isActiveRun(run)) return null
  if (run.scenarioId === 'update-tps' && (run.fixedUpdateEvidence?.version !== 2 || run.fixedUpdateEvidence?.verified !== true)) return null
  if (['revoke-tps', 'revoke-rate'].includes(run.scenarioId) && run.abnormalEvidence?.version !== 2) return null
  if (criterion?.id === 'revoke-rate' || run.scenarioId === 'revoke-rate') {
    return run.metricCheck?.collected === true ? run.metricCheck.value : null
  }
  return Number(run.summary?.totalRequests) > 0 ? run.summary.successfulRequestsPerSec : null
}
