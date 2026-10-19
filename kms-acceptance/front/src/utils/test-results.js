export const isActiveRun = run => ['preparing', 'running', 'queued', 'cancelling'].includes(run?.status)

export function securityOutcome(run) {
  if (!run) return { state: 'pending', label: '待测试' }
  if (isActiveRun(run)) return { state: 'running', label: run.status === 'cancelling' ? '正在停止' : '执行中' }
  if (run.status === 'completed' && run.verdict === 'blocked' && run.passed === true &&
      run.evidenceVersion === 2 && run.reasonMatched === true && run.legalControlPassed === true &&
      run.expectedCode && run.expectedCode === run.actualCode && run.expectedReason && run.expectedReason === run.actualReason) {
    return { state: 'passed', label: run.caseId?.startsWith('pq-') ? '协议校验通过' : '防御成功' }
  }
  if (run.status === 'completed' && run.verdict === 'vulnerable') return { state: 'failed', label: '防御校验未通过' }
  return { state: 'incomplete', label: run.status === 'cancelled' ? '已停止' : '测试未完成' }
}

export function securityProgress(caseIds, latest, target) {
  const outcomes = caseIds.map(id => securityOutcome(latest.get(id)))
  const count = state => outcomes.filter(item => item.state === state).length
  const passedCount = count('passed'), pendingCount = count('pending')
  const runningCount = count('running'), failedCount = count('failed'), incompleteCount = count('incomplete')
  const protocolOnly = caseIds.length > 0 && caseIds.every(id => id.startsWith('pq-'))
  const thresholdMet = !protocolOnly && passedCount >= target
  let state = 'pending', statusLabel = '待测试'
  if (runningCount) { state = 'running'; statusLabel = '执行中' }
  else if (failedCount) { state = 'failed'; statusLabel = '存在未通过项' }
  else if (incompleteCount) { state = 'incomplete'; statusLabel = '有测试未完成' }
  else if (protocolOnly && passedCount === caseIds.length) { state = 'incomplete'; statusLabel = '协议通过，算法待验' }
  else if (caseIds.length && passedCount === caseIds.length && thresholdMet) { state = 'passed'; statusLabel = '全部防御成功' }
  else if (passedCount) { state = 'partial'; statusLabel = `已防御 ${passedCount}/${caseIds.length} 项` }
  const note = state === 'passed' ? `${passedCount} 项场景的拒绝断言通过，合法节点读取正常。`
    : pendingCount ? `还有 ${pendingCount} 项待测试；验收下限为 ${target} 类。` : ''
  return { state, statusLabel, passedCount, pendingCount, runningCount, failedCount, incompleteCount, thresholdMet, note }
}

export function performanceOutcome(run) {
  if (!run) return { state: 'pending', label: '待执行' }
  if (isActiveRun(run)) return { state: 'running', label: '执行中' }
  const needsFinalState = run.scenarioId === 'revoke-rate' || run.metricCheck?.enforced === true
  if (run.status === 'passed' && run.passedTps === true && (!needsFinalState || (run.metricCheck?.collected === true && run.metricCheck?.passed === true))) return { state: 'passed', label: '已通过' }
  if (run.status === 'failed' && !run.error && Number(run.summary?.totalRequests) > 0) return { state: 'failed', label: '未达到指标' }
  return { state: 'incomplete', label: run.status === 'cancelled' ? '已停止' : '测试未完成' }
}

export function measuredPerformance(run, criterion) {
  if (!run || isActiveRun(run)) return null
  if (criterion?.id === 'revoke-rate' || run.scenarioId === 'revoke-rate') {
    return run.metricCheck?.collected === true ? run.metricCheck.value : null
  }
  return Number(run.summary?.totalRequests) > 0 ? run.summary.successfulRequestsPerSec : null
}
