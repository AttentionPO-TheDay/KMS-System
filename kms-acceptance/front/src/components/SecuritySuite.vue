<template>
  <div class="security-wrapper">
    <div class="panel-header">
      <div>
        <h2>当前系统安全协议测试</h2>
        <p class="subtitle">围绕生成签发、抗量子方案参数与无密码会话边界进行固定探针测试。不代表完整渗透测试或抗量子安全证明。</p>
      </div>
      <span class="badge" :class="health?.securityAvailable ? 'ok' : 'warn'">
        {{ health?.securityAvailable ? '安全引擎已就绪' : '安全引擎未就绪' }}
      </span>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>
    <p v-else-if="health && !health.securityAvailable" class="warn-msg">当前仅检测到安全引擎未就绪；你仍可点击执行，由后端返回真实失败原因。</p>

    <div class="suite-grid">
      <article v-for="suite in securitySuites" :key="suite.id" class="suite-column">
        <div class="suite-header" :class="suite.accent">
          <h3>{{ suite.name }}</h3>
          <span class="suite-count">{{ suite.cases.length }} 个用例</span>
        </div>
        <p class="suite-summary">{{ suite.summary }}</p>
        
        <div class="attack-list">
          <div v-for="item in suite.cases" :key="item.title" class="attack-card inner-glass">
            <div class="attack-head">
              <h4>{{ item.title }}</h4>
              <span v-if="item.caseId" class="badge" :class="verdictClass(item.caseId)">
                {{ verdictLabel(item.caseId) }}
              </span>
            </div>
            <div class="attack-meta">
              <span class="tag">{{ item.mode }}</span>
              <span><strong>目标：</strong> {{ item.target }}</span>
            </div>
            <p class="expected"><strong>预期：</strong> {{ item.expected }}</p>
            
            <ul class="steps">
              <li v-for="step in item.steps" :key="step">{{ step }}</li>
            </ul>

            <div v-if="item.caseId" class="attack-actions">
              <button class="btn-ghost small"
                :disabled="Boolean(loadingCaseId) || !canRunAcceptance"
                @click="doSecurityRun(item.caseId)">
                {{ loadingCaseId === item.caseId ? '执行中...' : '执行协议测试' }}
              </button>
            </div>

            <!-- Result Box -->
            <SecurityResult v-if="item.caseId && displayedRun(item.caseId)" :run="displayedRun(item.caseId)" />
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { health, securityRuns, API, loadSecurityRuns } from '../store'
import { securitySuites } from '../config/securityCases'
import { canRunAcceptance } from '../api/demo-context'
import { isActiveRun, securityOutcome } from '../utils/test-results'
import SecurityResult from './SecurityResult.vue'

const loadingCaseId = ref('')
const error = ref('')
const localRuns = ref({})

function displayedRun(caseId) {
  return localRuns.value[caseId] || securityRuns.value.find(item => item.caseId === caseId) || null
}

function verdictLabel(caseId) {
  const item = displayedRun(caseId)
  if (loadingCaseId.value === caseId) return '执行中'
  return securityOutcome(item).label
}

function verdictClass(caseId) {
  const item = displayedRun(caseId)
  return { passed: 'ok', failed: 'accent-red', incomplete: 'warn', running: 'warn', pending: 'warn' }[securityOutcome(item).state]
}

async function doSecurityRun(caseId) {
  error.value = ''
  localRuns.value = { ...localRuns.value, [caseId]: null }
  loadingCaseId.value = caseId
  try {
    let run = await API.postSecurityRun({ caseId })
    localRuns.value = { ...localRuns.value, [caseId]: run }
    const deadline = Date.now() + 180000
    while (isActiveRun(run) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 700))
      run = await API.getSecurityRun(run.id)
      localRuns.value = { ...localRuns.value, [caseId]: run }
    }
    if (isActiveRun(run)) throw new Error('等待结果超时，请刷新页面查看最终状态')
    await loadSecurityRuns()
  } catch (err) {
    console.error(err)
    error.value = err.message || '运行失败'
  } finally {
    loadingCaseId.value = ''
  }
}
</script>

<style scoped>
.security-wrapper { grid-column: 1 / -1; }
.subtitle { color: var(--kms-text-tertiary); margin-top: 8px; font-size: 14px; }

.suite-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.suite-header {
  padding: 12px 16px;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.suite-header h3 { margin: 0; font-size: 16px; color: var(--kms-text-primary); }
.suite-count { font-size: 11px; font-weight: bold; }
.suite-summary { font-size: 13px; color: var(--kms-text-secondary); margin-bottom: 20px; min-height: 40px; }

.accent-red { background: var(--kms-danger-subtle); border-left: 3px solid var(--kms-danger); }
.accent-orange { background: var(--kms-warning-subtle); border-left: 3px solid var(--kms-warning); }

.attack-list { display: flex; flex-direction: column; gap: 16px; }
.attack-card {
  padding: 16px;
  border-radius: 8px;
  background: var(--kms-surface-2);
}
.attack-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.attack-head h4 { margin: 0; font-size: 15px; color: var(--kms-text-primary); }
.attack-meta { font-size: 12px; color: var(--kms-text-secondary); margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.tag { display: inline-block; background: var(--kms-border); padding: 2px 6px; border-radius: 4px; font-size: 11px; color:var(--kms-text-secondary); width: fit-content; }
.expected { font-size: 12px; color: var(--kms-text-secondary); background: var(--kms-info-subtle); padding: 8px; border-radius: 6px; margin-bottom: 12px; border-left: 2px solid var(--kms-brand);}

.steps { padding-left: 20px; font-size: 12px; color: var(--kms-text-secondary); margin-bottom: 16px; line-height: 1.5;}
.steps li { margin-bottom: 4px; }

.attack-actions { margin-top: 16px; text-align: right; }
.small { font-size: 11px; padding: 6px 12px; }

.attack-result {
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  background: var(--kms-surface-3);
  font-size: 12px;
}
.attack-result p { margin: 0 0 6px 0; color: var(--kms-text-secondary); }
.attack-result.ok { border-top: 2px solid var(--kms-success); }
.attack-result.accent-orange { border-top: 2px solid var(--kms-warning); }

.result-header { font-weight: bold; margin-bottom: 8px; letter-spacing: 1px; }
.raw-output summary { color: var(--kms-brand-text); cursor: pointer; margin-top: 8px;}
.raw-output pre {
  background: var(--kms-text-primary); padding: 12px; color: var(--kms-text-secondary); border-radius: 4px; overflow-x: auto; font-family: monospace; font-size: 11px; margin-top: 8px;
}

.error-msg {
  color: var(--kms-danger-strong);
  margin: 16px 0;
  font-size: 13px;
}

.warn-msg {
  color: var(--kms-warning-strong);
  margin: 16px 0;
  font-size: 13px;
}

@media (max-width: 1024px) {
  .suite-grid { grid-template-columns: 1fr; }
}
</style>
