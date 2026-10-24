<template>
  <section class="lattice-page" :aria-labelledby="`title-${caseId}`">
    <header class="page-heading">
      <div><p class="eyebrow">抗量子密钥分发系统 / 格预分配测试</p><h1 :id="`title-${caseId}`">{{ current.title }}</h1><p class="purpose">{{ current.purpose }}</p></div>
      <button class="btn-ghost" :disabled="loading || running" @click="refresh">刷新记录</button>
    </header>
    <nav class="case-nav" aria-label="格预分配测试项">
      <router-link v-for="item in latticeCases" :key="item.id" :to="`/lattice/${item.id}`"><span>{{ item.stage }}</span>{{ item.title }}</router-link>
    </nav>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="loading" class="loading-message" role="status">正在读取测试环境和执行记录…</p>

    <div class="test-layout">
      <section class="setup-section" aria-labelledby="setup-title">
        <h2 id="setup-title">测试配置</h2>
        <form @submit.prevent="execute">
          <template v-if="caseId === 'basis-delegation'">
            <label for="root-id">离线主格参数</label>
            <select id="root-id" v-model="rootId" required :disabled="running || !roots.length"><option value="" disabled>选择已生成的主格参数</option><option v-for="row in roots" :key="row.id" :value="row.id">{{ short(row.id) }} · {{ time(row.createdAt) }}</option></select>
            <p v-if="!loading && !roots.length" class="prerequisite">先在“离线生成格陷门”页面生成主格参数。</p>
            <label for="node-id">绑定节点</label>
            <select id="node-id" v-model="nodeId" required :disabled="running || !catalog.nodes?.length"><option value="" disabled>选择节点</option><option v-for="node in catalog.nodes" :key="node.id" :value="node.id">{{ node.name }} · {{ node.id }}</option></select>
            <p v-if="!loading && !catalog.nodes?.length" class="prerequisite">暂无可选节点，请先完成节点登记。</p>
          </template>
          <template v-if="caseId === 'parallel-sampling'">
            <label for="preparation-id">节点委派材料</label>
            <select id="preparation-id" v-model="preparationId" required :disabled="running || !delegations.length"><option value="" disabled>选择已准备的节点委派材料</option><option v-for="row in delegations" :key="row.id" :value="row.id">{{ row.nodeName }} · {{ row.nodeId }} · {{ short(row.id) }}</option></select>
            <p v-if="!loading && !delegations.length" class="prerequisite">先在“快速委派格基向量”页面准备节点委派材料。</p>
            <div class="parameter-row">
              <div><label for="sample-count">样本数</label><select id="sample-count" v-model.number="count" :disabled="running"><option v-for="n in [16, 32, 64]" :key="n" :value="n">{{ n }} 条</option></select></div>
              <div><label for="worker-count">并发数</label><select id="worker-count" v-model.number="workers" :disabled="running"><option v-for="n in [1, 2, 4, 8]" :key="n" :value="n">{{ n }} 个进程</option></select></div>
            </div>
          </template>
          <dl class="parameters"><div><dt>格维度 n</dt><dd>{{ catalog.n ?? '—' }}</dd></div><div><dt>模数 q</dt><dd>{{ catalog.q ?? '—' }}</dd></div><div><dt>参数档</dt><dd>功能验证</dd></div></dl>
          <button class="btn-primary execute-button" type="submit" :disabled="!ready || running || !canRunAcceptance">{{ running ? '正在执行…' : current.action }}</button>
        </form>
        <h2 class="flow-heading">测试流程</h2>
        <ol class="test-steps"><li v-for="step in current.steps" :key="step">{{ step }}</li></ol>
      </section>

      <section class="results-section" aria-labelledby="results-title" :aria-busy="running">
        <header class="section-heading"><h2 id="results-title">测试结果</h2><span class="status" :class="result ? (result.passed ? 'passed' : 'failed') : ''">{{ running ? '执行中' : result ? (result.passed ? '功能验证通过' : '未通过') : '待执行' }}</span></header>
        <ExecutionTrace :events="execution" :running="running" :previous="running && Boolean(result)" :spans="result?.workerSpans || []" />
        <template v-if="result">
          <section class="algorithm-process" aria-label="本项算法流程与关键输出">
            <dl class="algorithm-output">
              <div><dt>本次公共矩阵</dt><dd>{{ result.preparation?.n }} × {{ result.preparation?.dimension }} · q={{ result.preparation?.q }}</dd></div>
              <template v-if="caseId === 'offline-trapdoor'"><div><dt>核格关系 / 满秩</dt><dd>{{ result.kernelRelation === true ? '模关系成立' : '未通过' }} / {{ result.fullRank === true ? '满秩' : '未通过' }}</dd></div><div><dt>行列式指数 log_q |det(T)|</dt><dd>{{ result.determinantLogQ ?? '—' }}</dd></div></template>
              <template v-else-if="caseId === 'basis-delegation'"><div><dt>绑定节点</dt><dd>{{ result.preparation?.nodeName }} · {{ result.preparation?.nodeId }}</dd></div><div><dt>委派格关系 / 短原像</dt><dd>{{ result.kernelRelation === true ? '模关系成立' : '未通过' }} / {{ result.preimageVerified === true ? '有效' : '未通过' }}</dd></div></template>
              <template v-else><div><dt>有效短向量</dt><dd>{{ result.valid }} / {{ result.count }}</dd></div><div><dt>实际工作{{ workerUnit }} / 峰值在途任务</dt><dd>{{ result.usedWorkers }} / {{ result.peakInFlight }}</dd></div></template>
            </dl>
          </section>
          <details class="run-metadata"><summary>执行信息与材料引用</summary>
          <dl class="run-details"><div><dt>执行编号</dt><dd>{{ result.id }}</dd></div><div><dt>执行时间</dt><dd>{{ time(result.recordedAt) }}</dd></div><div><dt>总耗时</dt><dd>{{ decimal(result.durationMs) }} ms</dd></div><div v-if="result.generationMs !== undefined"><dt>陷门生成耗时</dt><dd>{{ decimal(result.generationMs) }} ms</dd></div><div v-if="result.delegationMs !== undefined"><dt>委派计算耗时</dt><dd>{{ decimal(result.delegationMs) }} ms{{ result.reused ? '（使用已有持久化记录）' : '' }}</dd></div><template v-if="result.samplingMs !== undefined"><div><dt>采样总耗时</dt><dd>{{ decimal(result.samplingMs) }} ms</dd></div><div><dt>有效短向量</dt><dd>{{ result.valid }} / {{ result.count }}</dd></div><div v-if="result.usedWorkers !== undefined"><dt>实际工作{{ workerUnit }}</dt><dd>{{ result.usedWorkers }} 个，峰值在途 {{ result.peakInFlight }} 个任务</dd></div><div v-if="result.computeMs !== undefined"><dt>计算及进程通信</dt><dd>{{ decimal(result.computeMs) }} ms</dd></div><div v-if="result.poolSetupMs !== undefined"><dt>执行器准备</dt><dd>{{ decimal(result.poolSetupMs) }} ms · {{ result.poolReused ? '复用进程及格基' : '首次加载格基' }}</dd></div><div><dt>采样速率</dt><dd>{{ decimal(result.valid * 1000 / result.samplingMs) }} 条/秒</dd></div></template><div><dt>公共参数摘要</dt><dd class="digest">{{ result.preparation?.publicDigest }}</dd></div></dl>
          </details>
        </template>
        <div class="table-scroll" tabindex="0" role="region" aria-label="预期结果与实测判定">
          <table><thead><tr><th>验证内容</th><th>预期结果</th><th>实际结果</th><th>判定</th></tr></thead><tbody><tr v-for="row in verdicts" :key="row.name"><th>{{ row.name }}</th><td>{{ row.expected }}</td><td>{{ row.actual || '待实测' }}</td><td :class="row.passed === true ? 'passed-text' : row.passed === false ? 'failed-text' : ''">{{ row.passed === true ? '通过' : row.passed === false ? '未通过' : '—' }}</td></tr></tbody></table>
        </div>
        <template v-if="result?.samples?.length">
          <div class="samples-heading"><h3>短向量样本</h3><span>共 {{ result.samples.length }} 条</span></div>
          <div class="table-scroll samples" tabindex="0" role="region" aria-label="短向量样本验证结果"><table><thead><tr><th>序号</th><th>保护包摘要</th><th>向量范数</th><th>长度上限</th><th>模 q 余数</th></tr></thead><tbody><tr v-for="sample in result.samples" :key="sample.index"><td>{{ sample.index + 1 }}</td><td><code :title="sample.packageDigest">{{ short(sample.packageDigest) }}</code></td><td>{{ decimal(sample.norm) }}</td><td>{{ decimal(sample.bound) }}</td><td>{{ sample.residual.every(n => n === 0) ? '全零' : '非零' }}</td></tr></tbody></table></div>
        </template>
        <div v-if="result" class="result-actions"><button class="btn-ghost" @click="download">导出本次证据</button><router-link v-if="caseId === 'offline-trapdoor'" to="/lattice/basis-delegation">下一项：快速委派格基向量 →</router-link><router-link v-if="caseId === 'basis-delegation'" to="/lattice/parallel-sampling">下一项：并行抽样短向量 →</router-link></div>
      </section>
    </div>

    <section class="history-section" aria-labelledby="history-title"><div class="section-heading"><h2 id="history-title">执行记录</h2><span>{{ history.length }} 次</span></div><p v-if="!history.length" class="empty-history">尚无本项执行记录。</p><div v-else class="table-scroll" tabindex="0" role="region" aria-label="本测试项执行记录"><table><thead><tr><th>执行时间</th><th>执行编号</th><th>耗时</th><th>结论</th><th>操作</th></tr></thead><tbody><tr v-for="row in history" :key="row.id"><td>{{ time(row.recordedAt) }}</td><td><code>{{ short(row.id) }}</code></td><td>{{ decimal(row.durationMs) }} ms</td><td>{{ row.passed ? '功能验证通过' : '未通过' }}</td><td><button class="text-button" :aria-label="`查看 ${row.id}`" @click="selectedId = row.id">查看结果</button></td></tr></tbody></table></div></section>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { API } from '../api'
import { canRunAcceptance } from '../api/demo-context'
import { latticeCases } from '../config/latticeCases'
import ExecutionTrace from '../components/ExecutionTrace.vue'
import { latticeExecution } from '../utils/execution-trace.js'

const props = defineProps({ caseId: { type: String, required: true } })
const catalog = ref({}), loading = ref(false), running = ref(false), error = ref('')
const rootId = ref(''), nodeId = ref(''), preparationId = ref(''), count = ref(32), workers = ref(4), selectedId = ref('')
const current = computed(() => latticeCases.find(item => item.id === props.caseId))
const roots = computed(() => (catalog.value.preparations || []).filter(row => row.kind === 'ROOT'))
const delegations = computed(() => (catalog.value.preparations || []).filter(row => row.kind === 'DELEGATED'))
const history = computed(() => (catalog.value.records || []).filter(row => row.caseId === props.caseId))
const result = computed(() => history.value.find(row => row.id === selectedId.value) || history.value[0])
const workerUnit = computed(() => result.value?.executionMode === 'process' ? '进程' : '线程')
const execution = computed(() => latticeExecution(result.value))
const ready = computed(() => !loading.value && Boolean(catalog.value.profile) && (props.caseId === 'offline-trapdoor' || (props.caseId === 'basis-delegation' ? rootId.value && nodeId.value : preparationId.value)))
const verdicts = computed(() => result.value?.checks || current.value.expectations.map(([name, expected]) => ({ name, expected })))

function short(value = '') { return value ? `${value.slice(0, 12)}…` : '—' }
function time(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—' }
function decimal(value) { return Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '—' }
async function refresh() {
  loading.value = true; error.value = ''
  try {
    const response = await API.getLattice()
    catalog.value = response.data
    if (!roots.value.some(row => row.id === rootId.value)) rootId.value = roots.value[0]?.id || ''
    if (!delegations.value.some(row => row.id === preparationId.value)) preparationId.value = delegations.value[0]?.id || ''
  } catch (e) { error.value = e.message || '读取格预分配测试记录失败' } finally { loading.value = false }
}
async function execute() {
  if (!ready.value || running.value || !canRunAcceptance.value) return
  running.value = true; error.value = ''
  const payload = { caseId: props.caseId }
  if (props.caseId === 'basis-delegation') Object.assign(payload, { rootId: rootId.value, nodeId: nodeId.value })
  if (props.caseId === 'parallel-sampling') Object.assign(payload, { preparationId: preparationId.value, count: count.value, workers: workers.value })
  try {
    const response = await API.runLattice(payload)
    if (response.data.preparation?.kind === 'ROOT') rootId.value = response.data.preparation.id
    if (response.data.preparation?.kind === 'DELEGATED') preparationId.value = response.data.preparation.id
    catalog.value.records = [response.data, ...(catalog.value.records || [])]
    selectedId.value = response.data.id
    await refresh()
  } catch (e) { error.value = e.message || '执行测试失败' } finally { running.value = false }
}
function download() {
  const url = URL.createObjectURL(new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = `${props.caseId}-${result.value.id}.json`; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(refresh)
watch(() => props.caseId, () => { selectedId.value = ''; refresh() })
</script>

<style scoped>
.lattice-page { max-width: 1280px; margin: 0 auto; }
h1, h2, h3, p { margin: 0; }
h1 { font-size: 28px; line-height: 1.4; margin: 8px 0; }
h2 { font-size: 17px; font-weight: 650; }
h3 { font-size: 14px; font-weight: 600; }
.page-heading, .section-heading, .samples-heading, .result-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-heading { align-items: flex-start; margin-bottom: 24px; }
.eyebrow, .purpose, .empty-history { color: var(--kms-text-secondary); line-height: 1.7; font-size: 13px; }
.eyebrow { font-size: 12px; }
.case-nav { display: flex; border-bottom: 1px solid var(--kms-border); margin-bottom: 28px; gap: 24px; }
.case-nav a { text-decoration: none; padding: 14px 0; color: var(--kms-text-secondary); font-size: 14px; border-bottom: 2px solid transparent; }
.case-nav a span { font-size: 11px; margin-right: 8px; color: var(--kms-text-tertiary); }
.case-nav .router-link-active { color: var(--kms-brand-text); border-bottom-color: var(--kms-brand); font-weight: 600; }
.test-layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 32px; }
.setup-section { padding-right: 28px; border-right: 1px solid var(--kms-border); min-width: 0; }
form { margin-top: 20px; }
label { display: block; font-size: 12px; color: var(--kms-text-secondary); margin: 16px 0 8px; }
select { width: 100%; min-height: 42px; border: 1px solid var(--kms-border-strong); border-radius: 7px; padding: 8px; color: var(--kms-text-primary); background: var(--kms-surface-1); font: inherit; font-size: 12px; }
.parameter-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.parameters { margin: 22px 0; font-size: 12px; }
.parameters > div, .run-details > div { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; }
dt { color: var(--kms-text-secondary); flex-shrink: 0; }
dd { margin: 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.execute-button { width: 100%; min-height: 42px; }
.scope { font-size: 11px; margin-top: 12px; }
.flow-heading { margin-top: 32px; }
.test-steps { padding-left: 20px; color: var(--kms-text-secondary); font-size: 12px; line-height: 1.8; }
.test-steps li { padding: 6px 0 6px 4px; }
.results-section { min-width: 0; }
.section-heading { margin-bottom: 20px; }
.status { font-size: 12px; padding: 5px 9px; border-radius: 5px; background: var(--kms-surface-3); color: var(--kms-text-secondary); }
.status.passed { color: var(--kms-success-strong); background: var(--kms-success-subtle); }
.status.failed { color: var(--kms-danger-strong); background: var(--kms-danger-subtle); }
.run-details { margin: 0 0 22px; font-size: 12px; }
.run-details > div { justify-content: flex-start; border-bottom: 1px solid var(--kms-border); }
.run-details dt { width: 110px; }
.digest, code { font-family: var(--kms-font-mono, monospace); font-size: 11px; }
.table-scroll { overflow-x: auto; border: 1px solid var(--kms-border); border-radius: 8px; background: var(--kms-surface-1); }
table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; line-height: 1.7; }
th, td { padding: 12px 14px; border-bottom: 1px solid var(--kms-border); vertical-align: top; }
thead th { background: var(--kms-surface-2); color: var(--kms-text-secondary); font-weight: 500; white-space: nowrap; }
tbody th { min-width: 90px; font-weight: 550; }
td { color: var(--kms-text-secondary); }
tr:last-child th, tr:last-child td { border-bottom: 0; }
.passed-text { color: var(--kms-success-strong); white-space: nowrap; }
.failed-text, .error-message { color: var(--kms-danger-strong); }
.error-message { border: 1px solid var(--kms-danger-border); background: var(--kms-danger-subtle); padding: 12px; border-radius: 7px; margin-bottom: 20px; font-size: 13px; }
.loading-message { color: var(--kms-text-secondary); margin-bottom: 16px; font-size: 12px; }
.prerequisite { font-size: 12px; margin: 8px 0; line-height: 1.7; color: var(--kms-warning-strong); }
.samples-heading { margin: 24px 0 12px; font-size: 12px; color: var(--kms-text-secondary); }
.samples { max-height: 330px; overflow-y: auto; }
.samples thead { position: sticky; top: 0; }
.samples td { white-space: nowrap; font-variant-numeric: tabular-nums; }
.algorithm-process { margin: 20px 0; }
.algorithm-process ol { padding-left: 20px; display: grid; gap: 12px; font-size: 12px; line-height: 1.7; }
.algorithm-process p { color: var(--kms-text-secondary); margin-top: 3px; max-width: 70ch; }
.algorithm-output { font-size: 12px; display: grid; gap: 10px; border-top: 1px solid var(--kms-border); margin-top: 16px; padding-top: 14px; }
.algorithm-output > div { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.algorithm-output dt { color: var(--kms-text-secondary); }
.algorithm-output dd { margin: 0; font-variant-numeric: tabular-nums; }
.run-metadata { margin: 18px 0; }
.run-metadata summary { cursor: pointer; color: var(--kms-brand-text); font-size: 12px; }
.result-actions { margin-top: 24px; flex-wrap: wrap; }
.result-actions a { color: var(--kms-brand-text); text-decoration: none; font-size: 12px; }
.history-section { border-top: 1px solid var(--kms-border); margin-top: 36px; padding-top: 24px; }
.history-section .section-heading span { font-size: 12px; color: var(--kms-text-secondary); }
.history-section td { white-space: nowrap; }
.text-button { border: 0; color: var(--kms-brand-text); background: transparent; cursor: pointer; font: inherit; padding: 4px; }
button:focus-visible, select:focus-visible, a:focus-visible, .table-scroll:focus-visible { outline: 2px solid var(--kms-brand); outline-offset: 3px; }
button:disabled, select:disabled { cursor: not-allowed; opacity: .6; }
@media (max-width: 900px) { .test-layout { grid-template-columns: 1fr; gap: 28px; } .setup-section { border-right: 0; border-bottom: 1px solid var(--kms-border); padding: 0 0 16px; } form { max-width: 520px; } }
@media (max-width: 580px) { h1 { font-size: 23px; } .case-nav { gap: 12px; flex-wrap: wrap; } .case-nav a { font-size: 12px; padding: 10px 0; } .case-nav a span { display: none; } .page-heading { flex-direction: column; gap: 12px; } .run-details > div { flex-direction: column; gap: 4px; } .run-details dt { width: auto; } th, td { padding: 10px; } }
</style>
