<template>
  <div class="history-wrapper glass-panel">
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
          <span class="badge" :class="item.status === 'passed' ? 'ok' : 'error'">{{ item.status }}</span>
        </div>

        <div class="history-metrics">
          <div class="metric-box">
            <span>TPS 峰值</span>
            <strong :class="item.status === 'passed'? 'text-ok' : 'text-error'">{{ item.summary.requestsPerSec?.toFixed?.(2) || '0.00' }}</strong>
            <small>TARGET: {{ item.targetTps }}</small>
          </div>
          <div class="metric-box">
            <span>AVG 延迟</span>
            <strong>{{ item.summary.avgLatencyMs?.toFixed?.(2) || '0.00' }} ms</strong>
          </div>
          <div class="metric-box">
            <span>P99 等候</span>
            <strong>{{ item.summary.p99LatencyMs?.toFixed?.(2) || '0.00' }} ms</strong>
          </div>
          <div class="metric-box">
            <span>回收探查/其他</span>
            <strong>{{ metricLabel(item) }}</strong>
          </div>
        </div>

        <details class="raw-output">
          <summary>查看节点 WRK OUTPUT 原始探针数据</summary>
          <pre><code>{{ item.summary.rawOutput }}</code></pre>
        </details>
      </article>
      <div v-if="runs.length === 0" class="empty-state">
        <div class="empty-icon">📡</div>
        <p>暂无系统探测流水线，请在左侧发起攻击链</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { runs } from '../store'

function metricLabel(item) {
  if (!item.metricCheck || !item.metricCheck.kind) {
    return '未采集 (NOT FOUND)'
  }
  return `${item.metricCheck.value?.toFixed?.(2) || item.metricCheck.value}% / ${item.metricCheck.target}%`
}
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
.history-list::-webkit-scrollbar-thumb { background: rgba(0, 242, 254, 0.2); border-radius: 4px; }

.history-item {
  background: rgba(14, 25, 41, 0.6);
  border: 1px solid rgba(0, 242, 254, 0.1);
  border-radius: 12px;
  padding: 20px;
  transition: all 0.3s ease;
}
.history-item:hover {
  border-color: rgba(0, 242, 254, 0.4);
  box-shadow: 0 4px 20px rgba(0, 242, 254, 0.05);
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
  color: #fff;
}
.timestamp {
  font-size: 12px;
  color: #64748b;
  font-family: monospace;
}
.history-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.metric-box {
  background: rgba(0, 0, 0, 0.2);
  padding: 12px 16px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}
.metric-box span {
  font-size: 11px;
  color: #8b9eb3;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.metric-box strong {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  color: #e2e8f0;
}
.metric-box small {
  margin-top: 4px;
  font-size: 10px;
  color: #64748b;
}
.text-ok { color: #00f2fe !important; text-shadow: 0 0 10px rgba(0, 242, 254, 0.4); }
.text-error { color: #ff4d4f !important; text-shadow: 0 0 10px rgba(255, 77, 79, 0.4); }

.raw-output {
  border-top: 1px dashed rgba(255, 255, 255, 0.1);
  padding-top: 12px;
}
.raw-output summary {
  color: #00f2fe;
  cursor: pointer;
  font-size: 13px;
  user-select: none;
}
pre {
  background: #020617;
  color: #94a3b8;
  padding: 16px;
  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin-top: 12px;
}
</style>
