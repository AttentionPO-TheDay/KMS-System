<template>
  <section class="acceptance-workbench">
    <header class="workbench-header">
      <div>
        <h1>验收测试台</h1>
        <p class="lead">选择测试项目，查看执行过程与判定结果。</p>
      </div>
      <div class="header-actions">
        <span class="admin-label">Demo 管理员</span>
        <button class="btn-ghost small" :disabled="loading" @click="refresh">刷新看板</button>
        <button class="btn-primary" :disabled="busy || !canRunAcceptance" @click="runAll">执行全部可用项目</button>
      </div>
    </header>

    <section class="console-panel" aria-labelledby="performance-heading">
      <div class="section-heading">
        <div><h2 id="performance-heading">性能测试</h2><p class="section-description">按项目测量，保留执行阶段与测量证据。</p></div>
      </div>
      <div class="performance-list">
        <div class="performance-columns" aria-hidden="true"><span>测试项目</span><span>验收指标</span><span>状态</span><span>操作</span></div>
        <article v-for="item in performanceItems" :key="item.key" class="performance-item" :class="item.state" :data-criterion-id="item.id">
          <div class="performance-row">
            <div class="project-name"><h3>{{ item.title }}</h3><p>{{ item.evidenceSource }}</p></div>
            <span class="target-value">{{ item.targetLabel }}</span>
            <span class="item-status" :class="item.state">{{ item.statusLabel }}</span>
            <button v-if="item.running" class="btn-ghost small" @click="cancelItem(item)">停止任务</button>
            <button v-else class="btn-ghost small" :disabled="busy || !canRunAcceptance || !item.available" @click="runItem(item)">执行项目 <span aria-hidden="true">↗</span></button>
          </div>
          <PerformanceResult v-if="item.run" :run="item.run" :criterion="item" />
          <p v-if="item.note" class="item-note">{{ item.note }}</p>
        </article>
      </div>
    </section>

    <section class="security-panel" aria-labelledby="security-heading">
      <div class="section-heading"><div><h2 id="security-heading">安全测试</h2><p class="section-description">逐项查看请求过程、拒绝码与正常请求对照。</p></div></div>
      <div class="security-suites">
        <article v-for="(item, index) in securityItems" :key="item.key" class="security-suite" :class="item.state" :data-criterion-id="item.id">
          <div class="suite-controls">
            <div class="item-head"><span class="suite-index">0{{ index + 1 }}</span><span class="item-status" :class="item.state">{{ item.statusLabel }}</span></div>
            <h3>{{ item.title }}</h3>
            <p class="suite-description">{{ item.requirement }}</p>
            <div class="security-picker">
            <label :for="`security-case-${item.id}`">测试方式</label>
            <select :id="`security-case-${item.id}`" :value="selectedSecurityCase(item)" @change="selectedSecurityCases[item.id] = $event.target.value" :disabled="busy || item.running">
              <option value="">全部 {{ item.caseOptions.length }} 项测试</option>
              <option v-for="option in item.caseOptions" :key="option.caseId" :value="option.caseId">{{ option.title }}</option>
            </select>
            </div>
            <button v-if="item.running" class="btn-ghost small" @click="cancelItem(item)">停止任务</button>
            <button v-else class="btn-primary small" :disabled="busy || !canRunAcceptance || !item.available" @click="runItem(item)">{{ securityRunButtonLabel(item) }}</button>
            <p v-if="item.note" class="item-note" role="status">{{ item.note }}</p>
          </div>
          <div class="security-results">
            <div class="case-list-heading"><span>测试用例</span><span>执行结果</span></div>
            <ul class="case-results"><li v-for="(option, caseIndex) in item.caseOptions" :key="option.caseId" class="case-result">
              <div class="case-title"><span class="case-name"><span class="case-index">{{ String(caseIndex + 1).padStart(2, '0') }}</span><strong>{{ option.title }}</strong></span><span v-if="!option.run" class="pending-label">待测试</span></div>
              <SecurityResult v-if="option.run" :run="option.run" />
            </li></ul>
          </div>
        </article>
      </div>
      <p class="console-hint">安全测试使用独立临时会话，不改变业务密钥。抗量子协议校验不等同于量子攻击防御验证。</p>
    </section>

    <p v-if="error" class="error-msg" role="alert">{{ error }}</p>
    <section v-if="nodeItems.length" class="node-panel" aria-label="节点侧测试">
      <article v-for="item in nodeItems" :key="item.id" class="node-item"><div><span class="node-label">节点侧测试</span><h3>{{ item.title }}</h3><p>从节点侧单独发起测量，结果记录在验收看板。</p></div><span class="target-value">{{ item.targetLabel }}</span><span class="item-status" :class="item.state">{{ item.statusLabel }}</span></article>
    </section>

    <section class="dashboard-panel">
      <div class="section-heading"><h2>结果总览</h2><span class="updated-at">{{ updatedAt ? `更新于 ${updatedAt}` : '尚无执行结果' }}</span></div>
      <div class="summary-strip"><div><span>全部通过</span><strong>{{ summary.passed }}</strong></div><div><span>部分通过</span><strong>{{ summary.partial }}</strong></div><div><span>执行中</span><strong>{{ summary.running }}</strong></div><div><span>待执行</span><strong>{{ summary.pending }}</strong></div><div><span>测试未完成</span><strong>{{ summary.incomplete }}</strong></div><div><span>未通过</span><strong>{{ summary.failed }}</strong></div></div>
      <div class="result-table-wrap">
        <table class="result-table"><thead><tr><th>指标</th><th>目标</th><th>实测</th><th>状态</th><th>证据来源</th><th>执行时间</th><th>说明</th></tr></thead>
          <tbody><tr v-for="row in resultRows" :key="row.id" :class="row.state"><td><strong>{{ row.title }}</strong><small>{{ row.categoryLabel }}</small></td><td>{{ row.targetLabel }}</td><td>{{ row.valueLabel || '—' }}</td><td><span class="status-badge">{{ row.statusLabel }}</span></td><td>{{ row.source }}</td><td>{{ row.timeLabel }}</td><td>{{ row.note || '—' }}</td></tr></tbody>
        </table>
        <div v-if="!resultRows.length" class="empty-state">执行项目后，服务端实测值、判定状态和原始输出摘要会显示在这里。</div>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { acceptanceCriteria, acceptanceEvidence, scenarios, runs, securityRuns, health, API, loadAcceptanceEvidence, loadRuns, loadSecurityRuns } from '../store'
import { canRunAcceptance } from '../api/demo-context'
import { securitySuites } from '../config/securityCases'
import { securityProgress, performanceOutcome, measuredPerformance } from '../utils/test-results'
import SecurityResult from './SecurityResult.vue'
import PerformanceResult from './PerformanceResult.vue'

const loading = ref(false)
const busy = ref(false)
const error = ref('')
const updatedAt = ref('')
const selectedSecurityCases = ref({})
const securityCaseCatalog = new Map(securitySuites.flatMap(suite => suite.cases).map(item => [item.caseId, item]))

const latestBy = (items, field) => {
  const map = new Map()
  for (const item of items.value) if (!map.has(item[field])) map.set(item[field], item)
  return map
}
const latestRuns = computed(() => latestBy(runs, 'scenarioId'))
const latestSecurity = computed(() => latestBy(securityRuns, 'caseId'))
const latestEvidence = computed(() => latestBy(acceptanceEvidence, 'criterionId'))

const executableItems = computed(() => acceptanceCriteria.value.filter(c => c.kind !== 'evidence').map(c => {
  const scenario = c.scenarioId ? scenarios.value.find(s => s.id === c.scenarioId) : null
  const caseResults = (c.caseIds || []).map(id => latestSecurity.value.get(id)).filter(Boolean)
  const run = scenario ? latestRuns.value.get(scenario.id) : null
  const activeSecurityRun = caseResults.find(r => ['running', 'preparing'].includes(r.status))
  const running = Boolean(run && ['running', 'preparing'].includes(run.status)) || Boolean(activeSecurityRun)
  const progress = c.kind === 'security-suite' ? securityProgress(c.caseIds, latestSecurity.value, c.target) : null
  const outcome = progress || performanceOutcome(run)
  const available = c.kind === 'scenario' ? scenario?.available === true : securityAvailable.value
  const caseOptions = (c.caseIds || []).map(caseId => ({ ...(securityCaseCatalog.get(caseId) || { caseId, title: caseId }), run: latestSecurity.value.get(caseId) }))
  return { ...c, key: c.id, category: c.kind === 'security-suite' ? '安全用例组' : '性能场景', categoryLabel: c.kind === 'security-suite' ? '安全防御' : '性能验收', targetLabel: `${c.operator} ${formatValue(c.target, c.unit)}`, source: c.evidenceSource, caseOptions, available, running, run, progress, activeRunId: run && ['running', 'preparing'].includes(run.status) ? run.id : activeSecurityRun?.id, state: outcome.state, statusLabel: outcome.statusLabel || outcome.label, note: scenario?.unavailableReason || run?.error || caseResults.find(r => r.error)?.error || '' }
}))
const performanceItems = computed(() => executableItems.value.filter(item => item.kind === 'scenario'))
const securityItems = computed(() => executableItems.value.filter(item => item.kind === 'security-suite'))
const securityAvailable = computed(() => health.value?.securityExecutionAvailable === true || health.value?.securityAvailable === true)
const nodeItems = computed(() => acceptanceCriteria.value.filter(c => c.kind === 'evidence').map(c => { const item = latestEvidence.value.get(c.id); return { ...c, state: item?.verified ? (item.passed ? 'passed' : 'failed') : 'pending', statusLabel: item?.verified ? (item.passed ? '已通过' : '未达到') : '需节点验收', targetLabel: `${c.operator} ${formatValue(c.target, c.unit)}`, valueLabel: item ? formatValue(item.value, c.unit) : '', note: item?.evidence || '尚未执行独立节点验收' } }))
const resultRows = computed(() => [...executableItems.value, ...nodeItems.value].map(row => ({ ...row, valueLabel: row.valueLabel || valueFor(row), timeLabel: timeFor(row), source: row.source || row.evidenceSource })))
const summary = computed(() => resultRows.value.reduce((s, r) => { s[r.state] = (s[r.state] || 0) + 1; return s }, { passed: 0, partial: 0, running: 0, pending: 0, incomplete: 0, failed: 0 }))

function formatValue(value, unit) { return `${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit || ''}`.trim() }
function valueFor(row) { if (row.kind === 'scenario') { const value = measuredPerformance(latestRuns.value.get(row.scenarioId), row); return value === null ? '尚无有效测量' : formatValue(value, row.unit) } return row.progress?.passedCount ? `${row.progress.passedCount} 项${row.id === 'quantum-attacks' ? '协议校验通过，算法待验' : '防御成功'}` : '—' }
function timeFor(row) { const run = row.scenarioId ? latestRuns.value.get(row.scenarioId) : (row.caseIds || []).map(id => latestSecurity.value.get(id)).filter(Boolean).sort((a, b) => String(b.finishedAt || '').localeCompare(String(a.finishedAt || '')))[0]; return run?.finishedAt || latestEvidence.value.get(row.id)?.measuredAt || '' }
function selectedSecurityCase(item) { return selectedSecurityCases.value[item.id] || '' }
function securityCaseIds(item, forceAll = false) { const selected = selectedSecurityCase(item); return item.kind === 'security-suite' ? (!forceAll && selected ? [selected] : item.caseIds) : [] }
function securityRunButtonLabel(item) { if (item.kind !== 'security-suite') return '执行项目'; const selected = selectedSecurityCase(item); return selected ? '执行所选测试' : `执行全部 ${item.caseOptions.length} 项测试` }

async function runItem(item, { forceAll = false } = {}) {
  busy.value = true; error.value = ''
  try {
    let started = []
    if (item.kind === 'scenario') started = [await API.postRun({ scenarioId: item.scenarioId })]
    else {
      for (const caseId of securityCaseIds(item, forceAll)) {
        const run = await API.postSecurityRun({ caseId })
        started.push(run)
        await waitForCompletion([run.id])
      }
    }
    if (item.kind === 'scenario') await waitForCompletion(started.map(run => run.id).filter(Boolean))
  } catch (e) { error.value = e.message || '启动验收任务失败' } finally { busy.value = false }
}
async function runAll() { for (const item of executableItems.value.filter(i => i.available && !i.running)) await runItem(item, { forceAll: true }) }
async function cancelItem(item) { if (!item.activeRunId) return; error.value = ''; try { if (item.kind === 'scenario') await API.cancelRun(item.activeRunId); else await API.cancelSecurityRun(item.activeRunId); await refresh() } catch (e) { error.value = e.message || '停止任务失败' } }
async function refresh() { loading.value = true; try { await Promise.all([loadRuns(), loadSecurityRuns(), loadAcceptanceEvidence()]); updatedAt.value = new Date().toLocaleTimeString('zh-CN') } catch (e) { error.value = e.message || '看板刷新失败' } finally { loading.value = false } }
async function waitForCompletion(ids) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < 180000) {
    await refresh()
    const active = [...runs.value, ...securityRuns.value].some(run => ids.includes(run.id) && ['running', 'preparing'].includes(run.status))
    if (!active) return
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  throw new Error('任务超过前端轮询时限，请在结果看板查看最终状态')
}
</script>

<style scoped>
.acceptance-workbench { max-width: 1280px; margin: 0 auto; }
.workbench-header, .section-heading, .header-actions, .item-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.workbench-header { margin-bottom: 36px; align-items: flex-start; }
h1, h2, h3, p { margin: 0; }
h1, h2, h3 { color: var(--kms-text-primary); }
h1 { font-size: 28px; font-weight: 700; letter-spacing: -.025em; }
h2 { font-size: 18px; font-weight: 650; }
h3 { font-size: 14px; font-weight: 650; line-height: 1.6; }
.lead { margin-top: 8px; font-size: 13px; color: var(--kms-text-secondary); }
.header-actions { justify-content: flex-end; flex-wrap: wrap; }
.admin-label { font-size: 12px; color: var(--kms-text-tertiary); margin-right: 4px; }
button { min-height: 36px; transition: background-color .18s ease-out, border-color .18s ease-out, color .18s ease-out; }
button:focus-visible, select:focus-visible { outline: 2px solid var(--kms-brand); outline-offset: 3px; }
.small, .header-actions .btn-primary { padding: 8px 14px; font-size: 12px; }
.console-panel, .security-panel, .node-panel { margin-bottom: 32px; }
.section-heading { margin-bottom: 16px; }
.section-description { margin-top: 5px; font-size: 12px; color: var(--kms-text-tertiary); line-height: 1.6; }
.performance-list { border: 1px solid var(--kms-border); border-radius: 12px; background: var(--kms-surface-1); overflow: hidden; }
.performance-columns, .performance-row { display: grid; grid-template-columns: minmax(240px, 1fr) 190px 130px 110px; align-items: center; gap: 24px; padding: 16px 24px; }
.performance-columns { padding-top: 12px; padding-bottom: 12px; font-size: 11px; color: var(--kms-text-tertiary); background: var(--kms-surface-2); }
.performance-columns > :last-child { text-align: right; }
.performance-item { border-top: 1px solid var(--kms-border); }
.performance-item .performance-result, .performance-item > .item-note { margin: 0 24px 20px; }
.performance-row > button { justify-self: end; display: inline-flex; align-items: center; gap: 14px; }
.project-name p { color: var(--kms-text-tertiary); font-size: 11px; margin-top: 3px; overflow-wrap: anywhere; }
.target-value { font-size: 13px; color: var(--kms-text-primary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.item-status { display: inline-flex; align-items: center; justify-content: center; gap: 6px; justify-self: start; width: fit-content; font-size: 11px; font-weight: 500; color: var(--kms-text-secondary); background: var(--kms-surface-3); padding: 4px 9px; border-radius: 6px; white-space: nowrap; }
.item-status::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.item-status.passed { color: var(--kms-success-strong); background: var(--kms-success-subtle); }
.item-status.failed { color: var(--kms-danger-strong); background: var(--kms-danger-subtle); }
.item-status.running, .item-status.partial, .item-status.incomplete { color: var(--kms-warning-strong); background: var(--kms-warning-subtle); }
.security-suites { display: flex; flex-direction: column; gap: 16px; }
.security-suite { display: grid; grid-template-columns: 276px minmax(0, 1fr); border: 1px solid var(--kms-border); border-radius: 12px; background: var(--kms-surface-1); overflow: hidden; align-items: start; }
.suite-controls { padding: 24px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.suite-index { font-size: 12px; font-weight: 600; color: var(--kms-text-tertiary); font-variant-numeric: tabular-nums; letter-spacing: .08em; }
.suite-controls h3 { font-size: 16px; margin-top: 2px; }
.suite-description { font-size: 12px; line-height: 1.7; color: var(--kms-text-secondary); }
.security-picker { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.security-picker label { font-size: 11px; color: var(--kms-text-secondary); }
.security-picker select { width: 100%; min-height: 38px; border: 1px solid var(--kms-border-strong); border-radius: 7px; background: var(--kms-surface-1); color: var(--kms-text-primary); font: inherit; font-size: 12px; padding: 8px 10px; }
.suite-controls > button { width: 100%; }
.security-results { padding: 8px 24px 0; border-left: 1px solid var(--kms-border); min-width: 0; align-self: stretch; }
.case-list-heading { display: flex; justify-content: space-between; padding: 12px 0; font-size: 11px; color: var(--kms-text-tertiary); }
.case-results { list-style: none; margin: 0; padding: 0; }
.case-result { padding: 18px 0; border-top: 1px solid var(--kms-border); }
.case-title, .case-name { display: flex; align-items: center; gap: 12px; }
.case-title { justify-content: space-between; font-size: 13px; line-height: 1.6; }
.case-name strong { font-weight: 550; }
.case-index { color: var(--kms-text-tertiary); font-size: 11px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.pending-label { color: var(--kms-text-tertiary); font-size: 11px; white-space: nowrap; }
.console-hint { font-size: 11px; color: var(--kms-text-tertiary); margin-top: 12px; line-height: 1.7; }
.item-note { font-size: 12px; line-height: 1.7; color: var(--kms-warning-strong); overflow-wrap: anywhere; }
.error-msg { padding: 12px 16px; border: 1px solid var(--kms-danger-border); border-radius: 8px; background: var(--kms-danger-subtle); color: var(--kms-danger-strong); font-size: 13px; margin-bottom: 24px; }
.node-panel { border: 1px solid var(--kms-border); background: var(--kms-surface-2); border-radius: 10px; }
.node-item { display: grid; grid-template-columns: 1fr 190px 130px; gap: 24px; align-items: center; padding: 20px 24px; }
.node-label { font-size: 11px; color: var(--kms-text-tertiary); }
.node-item h3 { margin-top: 3px; }
.node-item p { font-size: 12px; color: var(--kms-text-secondary); margin-top: 4px; line-height: 1.6; }
.dashboard-panel { padding-top: 4px; }
.updated-at { font-size: 11px; color: var(--kms-text-tertiary); }
.summary-strip { display: flex; flex-wrap: wrap; gap: 12px 28px; padding: 16px 0; border-top: 1px solid var(--kms-border); }
.summary-strip > div { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--kms-text-secondary); }
.summary-strip strong { font-size: 14px; color: var(--kms-text-primary); font-variant-numeric: tabular-nums; font-weight: 600; }
.result-table-wrap { overflow-x: auto; border: 1px solid var(--kms-border); border-radius: 10px; background: var(--kms-surface-1); }
.result-table { width: 100%; border-collapse: collapse; font-size: 12px; line-height: 1.6; }
.result-table th { text-align: left; font-weight: 500; color: var(--kms-text-tertiary); background: var(--kms-surface-2); white-space: nowrap; }
.result-table td, .result-table th { padding: 14px 16px; border-bottom: 1px solid var(--kms-border); vertical-align: top; }
.result-table td { color: var(--kms-text-secondary); min-width: 90px; }
.result-table td:first-child { min-width: 160px; }
.result-table tbody tr:last-child td { border-bottom: 0; }
.result-table td strong { display: block; color: var(--kms-text-primary); font-weight: 550; }
.result-table td small { display: block; color: var(--kms-text-tertiary); font-size: 10px; margin-top: 3px; }
.result-table tr.passed .status-badge { color: var(--kms-success-strong); }
.result-table tr.failed .status-badge { color: var(--kms-danger-strong); }
.result-table tr.running .status-badge, .result-table tr.incomplete .status-badge, .result-table tr.partial .status-badge { color: var(--kms-warning-strong); }
.empty-state { padding: 24px; font-size: 13px; color: var(--kms-text-tertiary); }
@media (max-width: 1100px) {
  .performance-columns, .performance-row { grid-template-columns: minmax(190px, 1fr) 150px 110px 100px; gap: 16px; }
  .security-suite { grid-template-columns: 240px minmax(0, 1fr); }
  .suite-controls, .security-results { padding-left: 20px; padding-right: 20px; }
}
@media (max-width: 800px) {
  .workbench-header { flex-direction: column; gap: 20px; }
  .header-actions { justify-content: flex-start; }
  .performance-columns { display: none; }
  .performance-row { grid-template-columns: 1fr auto; gap: 12px; padding: 20px; }
  .project-name { grid-column: 1; }
  .performance-row .target-value { grid-column: 1; grid-row: 2; }
  .performance-row .item-status { grid-column: 2; grid-row: 1; justify-self: end; }
  .performance-row > button { grid-column: 2; grid-row: 2; }
  .performance-item:first-of-type { border-top: 0; }
  .security-suite { grid-template-columns: 1fr; }
  .security-results { border-left: 0; border-top: 1px solid var(--kms-border); }
  .node-item { grid-template-columns: 1fr auto; gap: 16px; }
  .node-item > div { grid-column: 1 / -1; }
  .node-item .item-status { justify-self: end; }
}
</style>
