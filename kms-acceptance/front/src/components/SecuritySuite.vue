<template>
  <div class="security-wrapper glass-panel">
    <div class="panel-header">
      <div>
        <h2>全维漏洞防护安全靶场</h2>
        <p class="subtitle">针对 3 类常见生成攻击与 5 类高频更新攻击进行真实业务层入侵防御探测。</p>
      </div>
      <span class="badge" :class="health?.securityAvailable ? 'ok' : 'warn'">
        {{ health?.securityAvailable ? '🛡️ 安全引擎已就绪' : '安全引擎未就绪' }}
      </span>
    </div>

    <p v-if="error" class="error-msg">⚠️ {{ error }}</p>
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
              <span><strong>🎯 目标：</strong> {{ item.target }}</span>
            </div>
            <p class="expected"><strong>💡 预期：</strong> {{ item.expected }}</p>
            
            <ul class="steps">
              <li v-for="step in item.steps" :key="step">{{ step }}</li>
            </ul>

            <div v-if="item.caseId" class="attack-actions">
              <button class="btn-ghost small"
                :disabled="loadingCaseId === item.caseId"
                @click="doSecurityRun(item.caseId)">
                {{ loadingCaseId === item.caseId ? '执行中...' : '执行真实攻击' }}
              </button>
            </div>

            <!-- Result Box -->
            <div v-if="item.caseId && displayedRun(item.caseId)" class="attack-result" :class="verdictClass(item.caseId)">
              <div class="result-header">🔍 本次执行结论</div>
              <p><strong>结论：</strong> {{ displayedRun(item.caseId).summary }}</p>
              <p v-if="displayedRun(item.caseId).error"><strong>异常：</strong> {{ displayedRun(item.caseId).error }}</p>
              <details v-if="displayedRun(item.caseId).requests?.length" class="raw-output">
                <summary>查看本次请求详情</summary>
                <pre>{{ JSON.stringify(displayedRun(item.caseId).requests, null, 2) }}</pre>
              </details>
            </div>
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

const loadingCaseId = ref('')
const error = ref('')
const localRuns = ref({})

function displayedRun(caseId) {
  return localRuns.value[caseId] || null
}

function hasHistory(caseId) {
  return securityRuns.value.some((item) => item.caseId === caseId)
}

function verdictLabel(caseId) {
  const item = displayedRun(caseId)
  if (loadingCaseId.value === caseId) return '执行中'
  if (!item) return hasHistory(caseId) ? '待重新执行' : '待执行'
  if (item.status === 'error') return '执行异常'
  return item.passed ? '防御成功' : '防御失败'
}

function verdictClass(caseId) {
  const item = displayedRun(caseId)
  if (!item) return 'warn'
  if (item.status === 'error') return 'accent-red'
  return item.passed ? 'ok' : 'accent-orange'
}

async function doSecurityRun(caseId) {
  error.value = ''
  localRuns.value = { ...localRuns.value, [caseId]: null }
  loadingCaseId.value = caseId
  try {
    const run = await API.postSecurityRun({ caseId })
    localRuns.value = { ...localRuns.value, [caseId]: run }
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
.subtitle { color: #8b9eb3; margin-top: 8px; font-size: 14px; }

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
.suite-header h3 { margin: 0; font-size: 16px; color: #fff; }
.suite-count { font-size: 11px; font-weight: bold; }
.suite-summary { font-size: 13px; color: #94a3b8; margin-bottom: 20px; min-height: 40px; }

.accent-red { background: linear-gradient(90deg, rgba(220, 38, 38, 0.4), transparent); border-left: 3px solid #ef4444; }
.accent-orange { background: linear-gradient(90deg, rgba(234, 88, 12, 0.4), transparent); border-left: 3px solid #f97316; }

.attack-list { display: flex; flex-direction: column; gap: 16px; }
.attack-card {
  padding: 16px;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
}
.attack-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.attack-head h4 { margin: 0; font-size: 15px; color: #e2e8f0; }
.attack-meta { font-size: 12px; color: #94a3b8; margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.tag { display: inline-block; background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 11px; color:#cbd5e1; width: fit-content; }
.expected { font-size: 12px; color: #bae6fd; background: rgba(2, 132, 199, 0.2); padding: 8px; border-radius: 6px; margin-bottom: 12px; border-left: 2px solid #0ea5e9;}

.steps { padding-left: 20px; font-size: 12px; color: #cbd5e1; margin-bottom: 16px; line-height: 1.5;}
.steps li { margin-bottom: 4px; }

.attack-actions { margin-top: 16px; text-align: right; }
.small { font-size: 11px; padding: 6px 12px; }

.attack-result {
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  background: rgba(0,0,0,0.4);
  font-size: 12px;
}
.attack-result p { margin: 0 0 6px 0; color: #cbd5e1; }
.attack-result.ok { border-top: 2px solid #10b981; }
.attack-result.accent-orange { border-top: 2px solid #f97316; }

.result-header { font-weight: bold; margin-bottom: 8px; letter-spacing: 1px; }
.raw-output summary { color: #4facfe; cursor: pointer; margin-top: 8px;}
.raw-output pre {
  background: #000; padding: 12px; color: #a1a1aa; border-radius: 4px; overflow-x: auto; font-family: monospace; font-size: 11px; margin-top: 8px;
}

.error-msg {
  color: #ff6b6b;
  margin: 16px 0;
  font-size: 13px;
}

.warn-msg {
  color: #fbbf24;
  margin: 16px 0;
  font-size: 13px;
}

@media (max-width: 1024px) {
  .suite-grid { grid-template-columns: 1fr; }
}
</style>
