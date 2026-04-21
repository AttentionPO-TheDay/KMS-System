<template>
  <div class="runner-wrapper glass-panel">
    <div class="panel-header">
      <h2>压测控制台</h2>
      <div class="status-indicator" :class="health?.wrkAvailable ? 'healthy' : 'error'">
        <span class="status-dot"></span>
        {{ health?.wrkAvailable ? 'Worker Ready' : 'Wrk Not Found' }}
      </div>
    </div>

    <div class="grid-form">
      <!-- Left Column -->
      <div class="form-core">
        <label class="field">
          <span>压测靶场场景</span>
          <div class="select-wrapper">
            <select v-model="form.scenarioId" @change="onScenarioChange">
              <option v-for="sc in scenarios" :key="sc.id" :value="sc.id">{{ sc.name }}</option>
            </select>
          </div>
        </label>
        
        <div v-if="activeScenario" class="scenario-note info-box">
          <p>{{ activeScenario.description }}</p>
          <ul><li v-for="n in activeScenario.notes || []" :key="n">{{ n }}</li></ul>
        </div>
        
        <div class="field-row">
          <label class="field">
            <span>基础接口 URL</span>
            <input v-model="form.baseUrl" class="tech-input"/>
          </label>
          <label class="field">
            <span>挂载路径 Path</span>
            <input v-model="form.path" class="tech-input"/>
          </label>
        </div>
        
        <div class="field-row triple">
          <label class="field">
            <span>线程数 (Threads)</span>
            <input v-model="form.threads" type="number" class="tech-input"/>
          </label>
          <label class="field">
            <span>连接数 (Conns)</span>
            <input v-model="form.connections" type="number" class="tech-input"/>
          </label>
          <label class="field">
            <span>压测时长 (Seconds)</span>
            <input v-model="form.durationSeconds" type="number" class="tech-input"/>
          </label>
        </div>
      </div>

      <!-- Right Column -->
      <div class="form-details">
        <label class="field">
          <span>Headers (按行)</span>
          <textarea v-model="form.headersText" rows="4" class="tech-input"></textarea>
        </label>
        <label class="field">
          <span>BODY 模板</span>
          <textarea v-model="form.body" rows="6" class="tech-input code"></textarea>
        </label>
        <div class="form-actions">
          <button class="btn-primary cyber-btn" :disabled="loading || !form.scenarioId" @click="doRun">
            <span class="cyber-btn-text">{{ loading ? '执行中...' : '启动测试' }}</span>
          </button>
          <button class="btn-ghost" @click="loadRuns">同步系统日志</button>
        </div>
        <p v-if="error" class="error-msg">⚠️ {{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { scenarios, health, API, loadRuns } from '../store'

const loading = ref(false)
const error = ref('')

const form = ref({
  scenarioId: '', baseUrl: '', path: '',
  threads: 12, connections: 400, durationSeconds: 30,
  body: '', headersText: '', wrkPath: ''
})

const activeScenario = computed(() => scenarios.value.find(s => s.id === form.value.scenarioId) || null)

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

async function doRun() {
  error.value = ''
  loading.value = true
  try {
    await API.postRun({
      scenarioId: form.value.scenarioId,
      baseUrl: form.value.baseUrl,
      path: form.value.path,
      threads: Number(form.value.threads),
      connections: Number(form.value.connections),
      durationSeconds: Number(form.value.durationSeconds),
      body: form.value.body,
      headers: form.value.headersText.split('\n').map(l => l.trim()).filter(Boolean),
      wrkPath: form.value.wrkPath
    })
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
  color: #ff4d4f;
  margin-top: 12px;
  font-size: 14px;
}
@media (max-width: 1024px) {
  .grid-form { grid-template-columns: 1fr; gap: 20px; }
}
</style>
