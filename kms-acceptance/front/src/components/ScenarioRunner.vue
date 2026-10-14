<template>
  <div class="runner-wrapper">
    <div class="panel-header">
      <div>
        <p class="panel-eyebrow">业务链路验收</p>
        <h2>压测控制台</h2>
      </div>
      <div class="status-indicator" :class="health?.boundaryProbeAvailable ? 'healthy' : 'error'">
        <span class="status-dot"></span>
        {{ health?.boundaryProbeAvailable ? '受控边界探针就绪' : '验收执行不可用' }}
      </div>
    </div>

    <div class="runner-primary">
      <label class="field scenario-field">
        <span>选择验收场景</span>
        <div class="select-wrapper">
          <select v-model="form.scenarioId" @change="onScenarioChange">
            <option v-for="sc in scenarios" :key="sc.id" :value="sc.id">{{ sc.name }}</option>
          </select>
        </div>
      </label>
      <div class="target-panel" v-if="activeScenario">
        <span>脚本目标</span>
        <strong>{{ activeScenario.id === 'demo-boundary-probe' ? '无业务副作用 / 权威与入口校验' : `${formatTps(activeScenario.targetTps)} TPS` }}</strong>
        <small>{{ activeScenario.method }} {{ activeScenario.path }}</small>
      </div>
      <div class="runner-actions">
        <button class="btn-primary cyber-btn" :disabled="loading || !canRunAcceptance || activeScenario?.available !== true" @click="doRun">
          {{ loading ? '执行中…' : '开始执行' }}
        </button>
        <button v-if="activeRun" class="btn-ghost" :disabled="loading" @click="cancelRun">停止探针</button>
        <button class="btn-ghost" @click="loadRuns">刷新历史</button>
      </div>
    </div>

    <div v-if="activeScenario" class="scenario-note info-box" :class="{ 'danger-note': isRevokeScenario }">
      <p>{{ activeScenario.description }}</p>
      <ul><li v-for="n in activeScenario.notes || []" :key="n">{{ n }}</li></ul>
      <strong v-if="isRevokeScenario">回收不可逆，仅允许使用验收专用密钥。</strong>
    </div>

    <details v-if="activeScenario?.configurable === true" class="advanced-panel">
      <summary>高级参数（默认脚本配置）</summary>
      <div class="grid-form">
        <div class="form-core">
          <div class="field-row">
            <label class="field"><span>基础接口 URL</span><input v-model="form.baseUrl" class="tech-input"/></label>
            <label class="field"><span>挂载路径 Path</span><input v-model="form.path" class="tech-input"/></label>
          </div>
          <div class="field-row triple">
            <label class="field"><span>线程数</span><input v-model="form.threads" type="number" min="1" class="tech-input"/></label>
            <label class="field"><span>连接数</span><input v-model="form.connections" type="number" min="1" class="tech-input"/></label>
            <label class="field"><span>压测时长（秒）</span><input v-model="form.durationSeconds" type="number" min="1" class="tech-input"/></label>
          </div>
        </div>
        <div class="form-details">
          <label class="field"><span>Headers（按行）</span><textarea v-model="form.headersText" rows="4" class="tech-input"></textarea></label>
          <label class="field"><span>BODY 模板</span><textarea v-model="form.body" rows="6" class="tech-input code"></textarea></label>
        </div>
      </div>
    </details>
    <p v-if="error" class="error-msg">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { scenarios, health, runs, API, loadRuns } from '../store'
import { canRunAcceptance } from '../api/demo-context'

const activeRun = computed(() => runs.value.find(run => run.status === 'running'))

const loading = ref(false)
const error = ref('')

const form = ref({
  scenarioId: '', baseUrl: '', path: '',
  threads: 12, connections: 400, durationSeconds: 30,
  body: '', headersText: '', wrkPath: ''
})

const activeScenario = computed(() => scenarios.value.find(s => s.id === form.value.scenarioId) || null)
const isRevokeScenario = computed(() => ['revoke-tps', 'revoke-rate'].includes(form.value.scenarioId))

watch(() => scenarios.value, (newVals) => {
  if (newVals.length > 0 && !form.value.scenarioId) {
    applyScenario(newVals[0])
  }
}, { immediate: true })

function applyScenario(sc) {
  if (!sc) return
  form.value.scenarioId = sc.id
  form.value.baseUrl = sc.baseUrl
  form.value.path = sc.path
  form.value.threads = sc.threads
  form.value.connections = sc.connections
  form.value.durationSeconds = sc.durationSeconds
  form.value.body = sc.bodyTemplate || ''
  form.value.headersText = Object.entries(sc.headers || {}).map(([k,v]) => `${k}: ${v}`).join('\n')
}

function onScenarioChange() {
  applyScenario(activeScenario.value)
}

function formatTps(value) {
  const n = Number(value || 0)
  return n >= 1000 ? `${Math.round(n / 1000)}k` : n.toLocaleString('zh-CN')
}

async function cancelRun() {
  if (!activeRun.value) return
  error.value = ''
  loading.value = true
  try { await API.cancelRun(activeRun.value.id); await loadRuns() }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}

async function doRun() {
  error.value = ''
  loading.value = true
  try {
    await API.postRun({ scenarioId: form.value.scenarioId })
    await loadRuns()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.runner-wrapper {
  padding: 30px;
  grid-column: 1 / -1;
  margin-bottom: 24px;
}
.panel-eyebrow { margin: 0 0 5px; color: var(--kms-brand-text); font-size: 11px; font-weight: 700; letter-spacing: .14em; }
.runner-primary { display: grid; grid-template-columns: minmax(260px, 1.4fr) minmax(180px, .8fr) auto; align-items: end; gap: 18px; }
.runner-primary .field { margin-bottom: 0; }
.target-panel { display: flex; flex-direction: column; gap: 4px; padding: 11px 14px; border: 1px solid var(--kms-border); border-radius: var(--kms-radius); background: var(--kms-surface-2); }
.target-panel span, .target-panel small { color: var(--kms-text-tertiary); font-size: 11px; }
.target-panel strong { color: var(--kms-text-primary); font-size: 18px; }
.runner-actions { display: flex; gap: 10px; }
.runner-actions button { white-space: nowrap; }
.advanced-panel { margin-top: 18px; border-top: 1px solid var(--kms-border); padding-top: 14px; }
.advanced-panel summary { cursor: pointer; color: var(--kms-text-secondary); font-size: 12px; font-weight: 600; }
.advanced-panel[open] summary { margin-bottom: 18px; }
.danger-note { background: var(--kms-warning-subtle); border-left-color: var(--kms-warning-strong); }
.danger-note strong { display: block; margin-top: 8px; color: var(--kms-warning-strong); font-size: 12px; }
.grid-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 40px;
  margin-top: 20px;
}
.form-actions {
  display: flex;
  gap: 16px;
  margin-top: 24px;
}
.error-msg {
  color: var(--kms-danger-strong);
  margin-top: 12px;
  font-size: 14px;
}
@media (max-width: 1024px) {
  .runner-primary { grid-template-columns: 1fr 1fr; }
  .runner-actions { grid-column: 1 / -1; }
  .grid-form { grid-template-columns: 1fr; gap: 20px; }
}
@media (max-width: 640px) {
  .runner-primary { grid-template-columns: 1fr; }
  .runner-actions { grid-column: auto; }
  .runner-actions button { flex: 1; }
}
</style>
