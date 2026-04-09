<script setup>
import { computed, onMounted, ref } from 'vue'

const scenarios = ref([])
const runs = ref([])
const health = ref(null)
const loading = ref(false)
const error = ref('')
const apiBase = import.meta.env.VITE_APP_ACCEPTANCE_API || '/acceptance-api'

const form = ref({
  scenarioId: '',
  baseUrl: '',
  path: '',
  threads: 12,
  connections: 400,
  durationSeconds: 30,
  body: '',
  headersText: '',
  wrkPath: ''
})

const activeScenario = computed(() => {
  return scenarios.value.find((item) => item.id === form.value.scenarioId) || null
})

const passCount = computed(() => runs.value.filter((item) => item.status === 'passed').length)

function applyScenario(scenario) {
  if (!scenario) {
    return
  }
  form.value.scenarioId = scenario.id
  form.value.baseUrl = scenario.baseUrl
  form.value.path = scenario.path
  form.value.threads = scenario.threads
  form.value.connections = scenario.connections
  form.value.durationSeconds = scenario.durationSeconds
  form.value.body = scenario.bodyTemplate
  form.value.headersText = Object.entries(scenario.headers || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join('\n')
}

async function loadHealth() {
  const response = await fetch(`${apiBase}/health`)
  health.value = await response.json()
}

async function loadScenarios() {
  const response = await fetch(`${apiBase}/scenarios`)
  const payload = await response.json()
  scenarios.value = payload.data || []
  if (!form.value.scenarioId && scenarios.value.length > 0) {
    applyScenario(scenarios.value[0])
  }
}

async function loadRuns() {
  const response = await fetch(`${apiBase}/runs`)
  const payload = await response.json()
  runs.value = payload.data || []
}

async function runScenario() {
  error.value = ''
  loading.value = true
  try {
    const response = await fetch(`${apiBase}/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        scenarioId: form.value.scenarioId,
        baseUrl: form.value.baseUrl,
        path: form.value.path,
        threads: Number(form.value.threads),
        connections: Number(form.value.connections),
        durationSeconds: Number(form.value.durationSeconds),
        body: form.value.body,
        headers: form.value.headersText
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        wrkPath: form.value.wrkPath
      })
    })

    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.message || payload.error || '执行失败')
    }
    await loadRuns()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function metricLabel(item) {
  if (!item.metricCheck || !item.metricCheck.kind) {
    return '未采集'
  }
  return `${item.metricCheck.value?.toFixed?.(2) || item.metricCheck.value}% / ${item.metricCheck.target}%`
}

onMounted(async () => {
  await Promise.all([loadHealth(), loadScenarios(), loadRuns()])
})
</script>

<template>
  <main class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">KMS Acceptance</p>
        <h1>测试系统</h1>
        <p class="hero-copy">
          独立前后端的测试系统，用于执行 `wrk` 压测、汇总 TPS 指标，并支撑联调验证与回收率判定。
        </p>
      </div>
      <div class="hero-cards">
        <article class="stat-card accent-green">
          <span>场景数</span>
          <strong>{{ scenarios.length }}</strong>
        </article>
        <article class="stat-card accent-blue">
          <span>历史执行</span>
          <strong>{{ runs.length }}</strong>
        </article>
        <article class="stat-card accent-purple">
          <span>通过次数</span>
          <strong>{{ passCount }}</strong>
        </article>
      </div>
    </section>

    <section class="grid two-columns">
      <article class="panel">
        <div class="panel-header">
          <h2>执行配置</h2>
          <span class="badge" :class="health?.wrkAvailable ? 'ok' : 'warn'">
            {{ health?.wrkAvailable ? 'wrk 已发现' : 'wrk 未发现' }}
          </span>
        </div>

        <label class="field">
          <span>测试场景</span>
          <select v-model="form.scenarioId" @change="applyScenario(activeScenario)">
            <option v-for="scenario in scenarios" :key="scenario.id" :value="scenario.id">
              {{ scenario.name }}
            </option>
          </select>
        </label>

        <div v-if="activeScenario" class="scenario-note">
          <p>{{ activeScenario.description }}</p>
          <ul>
            <li v-for="note in activeScenario.notes || []" :key="note">{{ note }}</li>
          </ul>
        </div>

        <div class="field-row">
          <label class="field">
            <span>Base URL</span>
            <input v-model="form.baseUrl" />
          </label>
          <label class="field">
            <span>Path</span>
            <input v-model="form.path" />
          </label>
        </div>

        <div class="field-row triple">
          <label class="field">
            <span>Threads</span>
            <input v-model="form.threads" type="number" min="1" />
          </label>
          <label class="field">
            <span>Connections</span>
            <input v-model="form.connections" type="number" min="1" />
          </label>
          <label class="field">
            <span>Duration(s)</span>
            <input v-model="form.durationSeconds" type="number" min="1" />
          </label>
        </div>

        <label class="field">
          <span>Headers</span>
          <textarea v-model="form.headersText" rows="4" />
        </label>

        <label class="field">
          <span>Request Body</span>
          <textarea v-model="form.body" rows="8" />
        </label>

        <label class="field">
          <span>Wrk Path</span>
          <input v-model="form.wrkPath" placeholder="为空则使用后端自动探测路径" />
        </label>

        <div class="actions">
          <button class="primary" :disabled="loading || !form.scenarioId" @click="runScenario">
            {{ loading ? '执行中...' : '启动测试' }}
          </button>
          <button class="ghost" @click="loadRuns">刷新历史</button>
        </div>
        <p v-if="error" class="error-text">{{ error }}</p>
      </article>

      <article class="panel status-panel">
        <div class="panel-header">
          <h2>运行环境</h2>
        </div>
        <dl class="meta-list">
          <div>
            <dt>服务状态</dt>
            <dd>{{ health?.status || '-' }}</dd>
          </div>
          <div>
            <dt>wrk 路径</dt>
            <dd>{{ health?.wrkPath || '未发现' }}</dd>
          </div>
          <div>
            <dt>结果目录</dt>
            <dd>{{ health?.dataDir || '-' }}</dd>
          </div>
          <div>
            <dt>时间</dt>
            <dd>{{ health?.now || '-' }}</dd>
          </div>
        </dl>
        <div class="callout">
          <h3>当前回收率口径</h3>
          <p>
            默认按 `kms-updatedel` 的 `/lifecycle/metrics` 计算受理回收率，适合验收附加系统快速落地；若你后续补了业务最终回收统计接口，这里可以直接切换。
          </p>
        </div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>执行历史</h2>
      </div>
      <div class="history-list">
        <article v-for="item in runs" :key="item.id" class="history-item">
          <div class="history-top">
            <div>
              <h3>{{ item.scenario }}</h3>
              <p>{{ item.startedAt }} <span v-if="item.finishedAt">-> {{ item.finishedAt }}</span></p>
            </div>
            <span class="badge" :class="item.status === 'passed' ? 'ok' : 'warn'">{{ item.status }}</span>
          </div>

          <div class="history-metrics">
            <div>
              <span>TPS</span>
              <strong>{{ item.summary.requestsPerSec?.toFixed?.(2) || '0.00' }}</strong>
              <small>目标 {{ item.targetTps }}</small>
            </div>
            <div>
              <span>平均延迟</span>
              <strong>{{ item.summary.avgLatencyMs?.toFixed?.(2) || '0.00' }} ms</strong>
            </div>
            <div>
              <span>P99</span>
              <strong>{{ item.summary.p99LatencyMs?.toFixed?.(2) || '0.00' }} ms</strong>
            </div>
            <div>
              <span>附加指标</span>
              <strong>{{ metricLabel(item) }}</strong>
            </div>
          </div>

          <details class="raw-output">
            <summary>查看 wrk 输出</summary>
            <pre>{{ item.summary.rawOutput }}</pre>
          </details>
        </article>
        <p v-if="runs.length === 0" class="empty-text">还没有测试记录。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page-shell {
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px 20px 64px;
}

.hero {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 12px;
  color: #7dd3fc;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  font-size: 12px;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: clamp(32px, 5vw, 52px);
  line-height: 1;
}

.hero-copy {
  margin-top: 16px;
  max-width: 760px;
  color: #9fb3c8;
  line-height: 1.7;
}

.hero-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card,
.panel,
.history-item {
  background: rgba(6, 18, 33, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(12px);
}

.stat-card {
  min-height: 132px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.stat-card span {
  color: #9fb3c8;
}

.stat-card strong {
  font-size: 38px;
}

.accent-green {
  background: linear-gradient(135deg, rgba(22, 101, 52, 0.45), rgba(6, 18, 33, 0.92));
}

.accent-blue {
  background: linear-gradient(135deg, rgba(14, 116, 144, 0.45), rgba(6, 18, 33, 0.92));
}

.accent-purple {
  background: linear-gradient(135deg, rgba(91, 33, 182, 0.45), rgba(6, 18, 33, 0.92));
}

.grid.two-columns {
  display: grid;
  grid-template-columns: 1.4fr 0.9fr;
  gap: 20px;
  margin-bottom: 24px;
}

.panel {
  padding: 24px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.badge {
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid transparent;
}

.badge.ok {
  color: #86efac;
  background: rgba(20, 83, 45, 0.45);
  border-color: rgba(34, 197, 94, 0.3);
}

.badge.warn {
  color: #fde68a;
  background: rgba(120, 53, 15, 0.45);
  border-color: rgba(251, 191, 36, 0.3);
}

.field,
.meta-list div {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field {
  margin-bottom: 16px;
}

.field span,
.meta-list dt,
.history-metrics span,
.scenario-note li,
.history-top p,
.empty-text {
  color: #9fb3c8;
}

.field-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.field-row.triple {
  grid-template-columns: repeat(3, 1fr);
}

input,
textarea,
select {
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.78);
  color: #f8fafc;
  padding: 12px 14px;
}

textarea {
  resize: vertical;
  min-height: 110px;
}

.scenario-note,
.callout {
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(125, 211, 252, 0.16);
}

.scenario-note ul {
  margin: 12px 0 0;
  padding-left: 18px;
}

.meta-list {
  display: grid;
  gap: 16px;
  margin: 0 0 20px;
}

.meta-list dd {
  margin: 0;
  font-weight: 600;
  word-break: break-all;
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 12px 18px;
  cursor: pointer;
}

button.primary {
  background: linear-gradient(135deg, #38bdf8, #22c55e);
  color: #04111f;
  font-weight: 700;
}

button.ghost {
  background: rgba(15, 23, 42, 0.78);
  color: #e2e8f0;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-text {
  margin-top: 14px;
  color: #fca5a5;
}

.history-list {
  display: grid;
  gap: 16px;
}

.history-item {
  padding: 20px;
}

.history-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.history-metrics {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.history-metrics div {
  padding: 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.72);
}

.history-metrics strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

.history-metrics small {
  display: block;
  margin-top: 6px;
  color: #64748b;
}

.raw-output {
  margin-top: 16px;
}

.raw-output summary {
  cursor: pointer;
  color: #7dd3fc;
}

pre {
  margin: 12px 0 0;
  padding: 16px;
  overflow: auto;
  border-radius: 16px;
  background: #020617;
  color: #cbd5e1;
}

@media (max-width: 1024px) {
  .hero,
  .grid.two-columns {
    grid-template-columns: 1fr;
  }

  .history-metrics,
  .hero-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .page-shell {
    padding: 20px 14px 48px;
  }

  .field-row,
  .field-row.triple,
  .history-metrics,
  .hero-cards {
    grid-template-columns: 1fr;
  }

  .history-top,
  .panel-header,
  .actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
