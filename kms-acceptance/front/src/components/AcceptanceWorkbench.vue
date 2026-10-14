<template>
  <section class="acceptance-workbench">
    <header class="workbench-header">
      <div>
        <p class="eyebrow">DEMO ACCEPTANCE / CONTROL ROOM</p>
        <h1>验收执行平台</h1>
        <p class="lead">管理员从固定白名单启动验收脚本，任务完成后自动进入结果看板。日常业务操作不会自动触发验收或回传量化结果。</p>
      </div>
      <div class="header-actions">
        <span class="scope-label">受控身份</span>
        <strong>Demo 管理员</strong>
        <button class="btn-ghost small" :disabled="loading" @click="refresh">刷新看板</button>
      </div>
    </header>

    <section class="console-panel">
      <div class="section-heading">
        <div><p class="eyebrow">EXECUTION CONSOLE</p><h2>执行控制台</h2></div>
        <button class="btn-primary" :disabled="busy || !canRunAcceptance" @click="runAll">执行全部可用项目</button>
      </div>
      <p class="console-hint">用例针对当前无密码系统，使用独立临时会话，不改变业务密钥。服务不可用、接口不存在和旧版结果不计为通过。抗量子协议测试不证明量子攻击防御能力。</p>
      <div class="execution-grid">
        <article v-for="item in executableItems" :key="item.key" class="execution-item">
          <div class="item-head"><span class="item-category">{{ item.category }}</span><span class="item-status" :class="item.state">{{ item.statusLabel }}</span></div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.requirement }}</p>
          <div class="item-meta"><span>目标 {{ item.targetLabel }}</span><span>{{ item.evidenceSource }}</span></div>
          <div v-if="item.kind === 'security-suite'" class="security-picker">
            <label :for="`security-case-${item.id}`">测试方式</label>
            <select :id="`security-case-${item.id}`" :value="selectedSecurityCase(item)" @change="selectedSecurityCases[item.id] = $event.target.value" :disabled="busy || item.running">
              <option value="">全部 {{ item.caseOptions.length }} 项测试</option>
              <option v-for="option in item.caseOptions" :key="option.caseId" :value="option.caseId">{{ option.title }}（{{ option.caseId }}）</option>
            </select>
            <span>{{ securitySelectionHint(item) }}</span>
          </div>
          <button v-if="item.running" class="btn-ghost small" @click="cancelItem(item)">停止任务</button>
          <button v-else class="btn-primary small" :disabled="busy || !canRunAcceptance || !item.available" @click="runItem(item)">{{ securityRunButtonLabel(item) }}</button>
          <p v-if="item.note" class="item-note">{{ item.note }}</p>
        </article>
        <article v-for="item in nodeItems" :key="item.id" class="execution-item node-item">
          <div class="item-head"><span class="item-category">节点侧</span><span class="item-status" :class="item.state">{{ item.statusLabel }}</span></div>
          <h3>{{ item.title }}</h3><p>{{ item.requirement }}</p>
          <div class="item-meta"><span>目标 {{ item.targetLabel }}</span><span>{{ item.evidenceSource }}</span></div>
          <span class="node-action">本项未在管理端运行。需从独立节点验收流程单独发起，日常预分配不会触发或计入验收。</span>
        </article>
      </div>
      <p v-if="error" class="error-msg">{{ error }}</p>
    </section>

    <section class="dashboard-panel">
      <div class="section-heading"><div><p class="eyebrow">RESULT DASHBOARD</p><h2>执行结果看板</h2></div><span class="updated-at">{{ updatedAt ? `更新于 ${updatedAt}` : '尚无执行结果' }}</span></div>
      <div class="summary-strip"><div><span>通过</span><strong>{{ summary.passed }}</strong></div><div><span>执行中</span><strong>{{ summary.running }}</strong></div><div><span>待执行</span><strong>{{ summary.pending }}</strong></div><div><span>失败</span><strong>{{ summary.failed }}</strong></div></div>
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
  const passedCount = caseResults.filter(r => r.status === 'completed' && r.verdict === 'blocked' && r.passed === true).length
  const passed = c.kind === 'scenario' ? run?.status === 'passed' && run?.passedTps && (c.id !== 'revoke-rate' || run?.metricCheck?.passed) : caseResults.length === c.caseIds.length && passedCount >= c.target
  const available = c.kind === 'scenario' ? scenario?.available === true : securityAvailable.value
  const caseOptions = (c.caseIds || []).map(caseId => securityCaseCatalog.get(caseId) || { caseId, title: caseId })
  return { ...c, key: c.id, category: c.kind === 'security-suite' ? '安全用例组' : '性能场景', categoryLabel: c.kind === 'security-suite' ? '安全防御' : '性能验收', targetLabel: `${c.operator} ${formatValue(c.target, c.unit)}`, source: c.evidenceSource, caseOptions, available, running, activeRunId: run && ['running', 'preparing'].includes(run.status) ? run.id : activeSecurityRun?.id, state: running ? 'running' : passed ? 'passed' : (run || caseResults.length ? 'failed' : 'pending'), statusLabel: running ? '执行中' : passed ? '已通过' : (run || caseResults.length ? '需复核' : available ? '待执行' : '执行器不可用'), note: scenario?.unavailableReason || run?.error || caseResults.find(r => r.error)?.error || '' }
}))
const securityAvailable = computed(() => health.value?.securityExecutionAvailable === true || health.value?.securityAvailable === true)
const nodeItems = computed(() => acceptanceCriteria.value.filter(c => c.kind === 'evidence').map(c => { const item = latestEvidence.value.get(c.id); return { ...c, state: item?.verified ? (item.passed ? 'passed' : 'failed') : 'pending', statusLabel: item?.verified ? (item.passed ? '已通过' : '未达到') : '需节点验收', targetLabel: `${c.operator} ${formatValue(c.target, c.unit)}`, valueLabel: item ? formatValue(item.value, c.unit) : '', note: item?.evidence || '尚未执行独立节点验收' } }))
const resultRows = computed(() => [...executableItems.value, ...nodeItems.value].map(row => ({ ...row, valueLabel: row.valueLabel || valueFor(row), timeLabel: timeFor(row), source: row.source || row.evidenceSource })))
const summary = computed(() => resultRows.value.reduce((s, r) => { s[r.state] = (s[r.state] || 0) + 1; return s }, { passed: 0, running: 0, pending: 0, failed: 0 }))

function formatValue(value, unit) { return `${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit || ''}`.trim() }
function valueFor(row) { if (row.kind === 'scenario') { const run = latestRuns.value.get(row.scenarioId); return formatValue(row.id === 'revoke-rate' ? run?.metricCheck?.value : run?.summary?.successfulRequestsPerSec, row.unit) } const n = (row.caseIds || []).map(id => latestSecurity.value.get(id)).filter(Boolean).filter(r => r.passed).length; return n ? `${n}/${row.caseIds.length} 类` : '' }
function timeFor(row) { const run = row.scenarioId ? latestRuns.value.get(row.scenarioId) : (row.caseIds || []).map(id => latestSecurity.value.get(id)).filter(Boolean).sort((a, b) => String(b.finishedAt || '').localeCompare(String(a.finishedAt || '')))[0]; return run?.finishedAt || latestEvidence.value.get(row.id)?.measuredAt || '' }
function selectedSecurityCase(item) { return selectedSecurityCases.value[item.id] || '' }
function securityCaseIds(item, forceAll = false) { const selected = selectedSecurityCase(item); return item.kind === 'security-suite' ? (!forceAll && selected ? [selected] : item.caseIds) : [] }
function securitySelectionHint(item) { const selected = item.caseOptions.find(option => option.caseId === selectedSecurityCase(item)); return selected ? `本次仅执行：${selected.title}。${selected.expected}` : `直接执行将依次运行全部 ${item.caseOptions.length} 项协议测试` }
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
.acceptance-workbench{max-width:1280px;margin:0 auto}.workbench-header,.section-heading{display:flex;justify-content:space-between;gap:24px;align-items:flex-end}.workbench-header{align-items:flex-start;margin-bottom:24px}.eyebrow{margin:0 0 7px;color:var(--kms-brand-text);font-size:11px;font-weight:700;letter-spacing:.15em}.workbench-header h1,.section-heading h2,.execution-item h3{margin:0;color:var(--kms-text-primary)}.workbench-header h1{font-size:32px}.lead{max-width:760px;margin:8px 0 0;color:var(--kms-text-secondary);line-height:1.7}.header-actions{min-width:180px;padding:14px 16px;border:1px solid var(--kms-border);border-radius:var(--kms-radius);background:var(--kms-surface-1)}.scope-label,.header-actions strong{display:block}.scope-label{color:var(--kms-text-tertiary);font-size:11px}.header-actions strong{margin:5px 0 12px;color:var(--kms-text-primary)}.small{padding:8px 12px;font-size:12px}.console-panel,.dashboard-panel{padding:22px;border:1px solid var(--kms-border);border-radius:var(--kms-radius);background:var(--kms-surface-1);margin-bottom:22px}.section-heading h2{font-size:21px}.console-hint{margin:14px 0;color:var(--kms-text-tertiary);font-size:12px}.execution-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.execution-item{display:flex;flex-direction:column;gap:9px;padding:16px;border:1px solid var(--kms-border);background:var(--kms-surface-2)}.execution-item h3{font-size:15px}.execution-item p{margin:0;color:var(--kms-text-secondary);font-size:12px;line-height:1.55}.item-head{display:flex;justify-content:space-between}.item-category,.item-status,.item-meta,.node-action{font-size:11px}.item-category{color:var(--kms-brand-text)}.item-status{color:var(--kms-text-tertiary)}.item-status.passed{color:var(--kms-success-strong)}.item-status.failed{color:var(--kms-danger-strong)}.item-status.running{color:var(--kms-warning-strong)}.item-meta{display:flex;flex-direction:column;gap:4px;color:var(--kms-text-tertiary);margin-top:auto}.security-picker{display:flex;flex-direction:column;gap:6px}.security-picker label{color:var(--kms-text-secondary);font-size:11px;font-weight:600}.security-picker select{width:100%;min-height:36px;padding:7px 32px 7px 10px;border:1px solid var(--kms-border);border-radius:var(--kms-radius);background:var(--kms-surface-1);color:var(--kms-text-primary);font:inherit;font-size:12px}.security-picker select:focus{outline:2px solid var(--kms-brand-subtle);outline-offset:1px;border-color:var(--kms-brand)}.security-picker select:disabled{cursor:not-allowed;opacity:.6}.security-picker span{color:var(--kms-text-tertiary);font-size:11px;line-height:1.45}.item-note{color:var(--kms-warning-strong)!important}.node-action{padding-top:9px;color:var(--kms-text-tertiary);border-top:1px solid var(--kms-border)}.summary-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin:18px 0;border:1px solid var(--kms-border);background:var(--kms-border)}.summary-strip div{padding:13px 16px;background:var(--kms-surface-2)}.summary-strip span{display:block;color:var(--kms-text-tertiary);font-size:11px}.summary-strip strong{display:block;margin-top:5px;color:var(--kms-text-primary);font-size:22px}.updated-at{color:var(--kms-text-tertiary);font-size:11px}.result-table-wrap{overflow:auto}.result-table{width:100%;border-collapse:collapse;min-width:980px}.result-table th,.result-table td{padding:12px 10px;text-align:left;border-bottom:1px solid var(--kms-border);vertical-align:top;font-size:12px;color:var(--kms-text-secondary)}.result-table th{color:var(--kms-text-tertiary);font-size:11px;font-weight:600}.result-table td strong,.result-table td small{display:block}.result-table td strong{color:var(--kms-text-primary)}.result-table td small{margin-top:4px;color:var(--kms-text-tertiary)}.result-table tr.passed{background:var(--kms-success-subtle)}.result-table tr.failed{background:var(--kms-danger-subtle)}.result-table tr.running{background:var(--kms-warning-subtle)}.status-badge{font-weight:600}.passed .status-badge{color:var(--kms-success-strong)}.failed .status-badge{color:var(--kms-danger-strong)}.running .status-badge{color:var(--kms-warning-strong)}.empty-state{padding:34px;text-align:center;color:var(--kms-text-tertiary);font-size:12px}.error-msg{margin:12px 0 0;color:var(--kms-danger-strong);font-size:12px}@media(max-width:980px){.execution-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.workbench-header,.section-heading{flex-direction:column;align-items:flex-start}.execution-grid{grid-template-columns:1fr}.summary-strip{grid-template-columns:repeat(2,1fr)}.header-actions{width:100%;box-sizing:border-box}}
</style>
