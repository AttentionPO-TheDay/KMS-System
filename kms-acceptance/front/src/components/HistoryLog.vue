<template>
  <div class="history-wrapper">
    <div class="panel-header">
      <h2>集群测试流水</h2>
      <span class="badge cyber-badge">{{ runs.length }} LOGS</span>
    </div>

    <div class="history-list">
      <article v-for="item in runs" :key="item.id" class="history-item">
        <div class="history-top">
          <div>
            <h3>{{ item.scenario }}</h3>
            <p class="timestamp">{{ item.startedAt }} <span v-if="item.finishedAt">-> {{ item.finishedAt }}</span></p>
          </div>
          <span class="badge" :class="performanceOutcome(item).state === 'passed' ? 'ok' : 'warn'">{{ performanceOutcome(item).label }}</span>
        </div>

        <PerformanceResult :run="item" />
      </article>
      <div v-if="runs.length === 0" class="empty-state">
        <div class="empty-icon" aria-hidden="true"></div>
        <p>暂无压测流水，请在左侧发起压测任务</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { runs } from '../store'
import { performanceOutcome } from '../utils/test-results'
import PerformanceResult from './PerformanceResult.vue'
</script>

<style scoped>
.history-wrapper {
  grid-column: 1 / -1;
  margin-bottom: 24px;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 800px;
  overflow-y: auto;
  padding-right: 8px;
}
.history-list::-webkit-scrollbar { width: 6px; }
.history-list::-webkit-scrollbar-thumb { background: var(--kms-brand-subtle); border-radius: 4px; }

.history-item {
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-brand-subtle);
  border-radius: 12px;
  padding: 20px;
  transition: all 0.3s ease;
}
.history-item:hover {
  border-color: var(--kms-brand-border);
  box-shadow: 0 4px 20px var(--kms-brand-subtle);
  transform: translateY(-2px);
}
.history-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.history-top h3 {
  margin: 0 0 6px 0;
  font-size: 18px;
  color: var(--kms-text-primary);
}
.timestamp {
  font-size: 12px;
  color: var(--kms-text-tertiary);
  font-family: monospace;
}
.history-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.metric-box {
  background: var(--kms-surface-2);
  padding: 12px 16px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}
.metric-box span {
  font-size: 11px;
  color: var(--kms-text-tertiary);
  text-transform: uppercase;
  margin-bottom: 6px;
}
.metric-box strong {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  color: var(--kms-text-primary);
}
.metric-box small {
  margin-top: 4px;
  font-size: 10px;
  color: var(--kms-text-tertiary);
}
.text-ok { color: var(--kms-brand-text) !important; text-shadow: 0 0 10px var(--kms-brand-border); }
.text-error { color: var(--kms-danger-strong) !important; }

.raw-output {
  border-top: 1px dashed var(--kms-border);
  padding-top: 12px;
}
.raw-output summary {
  color: var(--kms-brand-text);
  cursor: pointer;
  font-size: 13px;
  user-select: none;
}
pre {
  background: var(--kms-surface-1);
  color: var(--kms-text-secondary);
  padding: 16px;
  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin-top: 12px;
}
</style>
