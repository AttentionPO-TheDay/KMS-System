<template>
  <section class="performance-result" :class="outcome.state">
    <div class="result-heading"><strong>{{ outcome.label }}</strong><time :title="run.finishedAt || run.startedAt">{{ formatTime(run.finishedAt || run.startedAt) }}</time></div>
    <dl>
      <div><dt>实测{{ unit === '%' ? '最终回收率' : '成功请求速率' }}</dt><dd>{{ value === null ? '尚无有效测量' : `${number(value)} ${unit}` }}</dd></div>
      <div><dt>验收要求</dt><dd>{{ operator }} {{ number(target) }} {{ unit }}</dd></div>
    </dl>
    <p v-if="run.error" class="result-error">{{ run.error }}</p>
    <p v-else-if="run.stage">{{ run.stage }}</p>
    <p>测试时间：{{ formatTime(run.startedAt) || '未开始' }} → {{ formatTime(run.finishedAt) || '进行中' }}</p>
    <details class="evidence-details" open>
      <summary>测试过程与测量证据</summary>
      <ol v-if="run.stages?.length"><li v-for="(step, index) in run.stages" :key="index">{{ formatTime(step.at) }} · {{ step.label }}</li></ol>
      <p v-else>此记录未采集逐阶段过程，可查看下方测量证据。</p>
      <dl>
        <div><dt>总请求数</dt><dd>{{ number(run.summary?.totalRequests) }}</dd></div>
        <div><dt>请求成功率</dt><dd>{{ value === null ? '未采集' : `${number(run.summary?.successRate)} %` }}</dd></div>
        <div><dt>非成功响应 / 连接错误</dt><dd>{{ number(run.summary?.non2xxResponses) }} / {{ number(run.summary?.socketErrors) }}</dd></div>
        <div><dt>平均 / P99 延迟</dt><dd>{{ value === null ? '未采集' : `${number(run.summary?.avgLatencyMs)} / ${number(run.summary?.p99LatencyMs)} ms` }}</dd></div>
      </dl>
      <p v-if="run.metricCheck?.message">最终状态核验：{{ run.metricCheck.message }}</p>
      <p v-if="run.metricCheck?.source">核验来源：{{ run.metricCheck.source }}</p>
      <p v-for="note in run.notes || []" :key="note">{{ note }}</p>
      <pre v-if="run.summary?.rawOutput">{{ run.summary.rawOutput }}</pre>
    </details>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { performanceOutcome, measuredPerformance } from '../utils/test-results'
const props = defineProps({ run: { type: Object, required: true }, criterion: { type: Object, default: null }, scenario: { type: Object, default: null } })
const outcome = computed(() => performanceOutcome(props.run))
const value = computed(() => measuredPerformance(props.run, props.criterion))
const unit = computed(() => props.criterion?.unit || (props.run.scenarioId === 'revoke-rate' ? '%' : 'TPS'))
const target = computed(() => props.criterion?.target ?? (unit.value === '%' ? props.run.metricCheck?.target : props.run.targetTps))
const operator = computed(() => props.criterion?.operator || props.scenario?.targetOperator || props.run.metricCheck?.operator || (['generate-tps', 'revoke-rate'].includes(props.run.scenarioId) ? '>' : '>='))
function number(value) { return value === null || value === undefined ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function formatTime(value) { if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour12: false }) }
</script>

<style scoped>
.performance-result { margin-top: 12px; padding-top: 16px; border-top: 1px solid var(--kms-border); font-size: 12px; line-height: 1.7; min-width: 0; }
.result-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.result-heading strong { font-size: 12px; color: var(--kms-text-secondary); }
.passed .result-heading strong { color: var(--kms-success-strong); }
.failed .result-heading strong, .result-error { color: var(--kms-danger-strong); }
.incomplete .result-heading strong, .running .result-heading strong { color: var(--kms-warning-strong); }
time { font-size: 11px; color: var(--kms-text-tertiary); }
dl { margin: 12px 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 24px; }
dl div { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
dt { color: var(--kms-text-tertiary); }
dd { margin: 0; color: var(--kms-text-primary); font-weight: 550; font-variant-numeric: tabular-nums; }
p { margin: 8px 0; overflow-wrap: anywhere; color: var(--kms-text-secondary); }
.evidence-details { margin-top: 14px; color: var(--kms-text-secondary); }
summary { cursor: pointer; color: var(--kms-brand-text); font-weight: 550; }
summary:focus-visible { outline: 2px solid var(--kms-brand); outline-offset: 3px; }
ol { padding-left: 20px; margin: 12px 0; color: var(--kms-text-secondary); }
li { padding: 4px 0 4px 4px; }
li::marker { color: var(--kms-text-tertiary); font-size: 11px; }
pre { max-height: 260px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--kms-font-mono); font-size: 11px; padding: 16px; background: var(--kms-surface-2); border-radius: 8px; border: 1px solid var(--kms-border); }
@media (max-width: 800px) { dl { grid-template-columns: 1fr; } }
</style>
