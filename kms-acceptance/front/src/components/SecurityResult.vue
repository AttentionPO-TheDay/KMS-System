<template>
  <section class="security-result" :class="outcome.state" :data-case-id="run.caseId">
    <div class="result-heading"><strong>{{ outcome.label }}</strong><time :title="run.finishedAt || run.startedAt">{{ formatTime(run.finishedAt || run.startedAt) }}</time></div>
    <p v-if="legacyEvidence">证据版本已过期，请重新执行。</p>
    <p v-else-if="run.error" class="result-error" role="status">{{ run.error }}</p>
    <p v-else-if="outcome.state !== 'running' && !run.testInput && !run.quantumEvidence">{{ run.summary || run.stage || '尚未获得完整判定证据。' }}</p>
    <dl v-if="controlChecks.length" class="control-checks" aria-label="合法业务核验">
      <div v-for="item in controlChecks" :key="item.name" class="control-check">
        <dt>{{ item.name }}</dt>
        <dd><strong :class="item.state">{{ item.state === 'success' ? '通过' : item.state === 'failed' ? '未通过' : '未完成' }}</strong><span>{{ item.detail }}</span></dd>
      </div>
    </dl>
    <ExecutionTrace :key="run.id" :events="execution" :running="outcome.state === 'running'" :stage="run.stage" />
    <QuantumEvidence v-if="run.quantumEvidence && outcome.state === 'evaluated'" :evidence="run.quantumEvidence" />

  </section>
</template>

<script setup>
import { computed } from 'vue'
import { securityOutcome } from '../utils/test-results'
import QuantumEvidence from './QuantumEvidence.vue'
import ExecutionTrace from './ExecutionTrace.vue'
import { securityExecution } from '../utils/execution-trace.js'
const props = defineProps({ run: { type: Object, required: true } })
const outcome = computed(() => securityOutcome(props.run))
const execution = computed(() => securityExecution(props.run))
const controlChecks = computed(() => (props.run.probeSteps || []).filter(step => step.kind === 'CONTROL'))
const legacyEvidence = computed(() => props.run.status === 'completed' && props.run.passed === true &&
  (props.run.caseId?.startsWith('pq-') ? props.run.evidenceVersion !== 3 : props.run.evidenceVersion !== 2))
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour12: false }) }
</script>

<style scoped>
.security-result { padding-top: 12px; font-size: 12px; line-height: 1.7; min-width: 0; }
.result-heading, .trace-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.result-heading strong { padding: 2px 8px; border-radius: 5px; font-size: 11px; font-weight: 600; color: var(--kms-text-secondary); background: var(--kms-surface-3); }
.core-evidence h4 { font-size: 12px; font-weight: 550; margin: 14px 0 6px; color: var(--kms-text-primary); }
.result-error { color: var(--kms-danger-strong); }
.control-status { margin: 10px 0; }
.control-checks { margin: 12px 0; border-top: 1px solid var(--kms-border); }
.control-check { display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--kms-border); }
.control-check dt { color: var(--kms-text-primary); font-size: 12px; }
.control-check dd { margin: 0; font-size: 11px; overflow-wrap: anywhere; }
.control-check dd strong { margin-right: 10px; }
.control-check dd span { color: var(--kms-text-secondary); }
.control-check .success { color: var(--kms-success-strong); }
.control-check .failed { color: var(--kms-danger-strong); }
.passed .result-heading strong { color: var(--kms-success-strong); background: var(--kms-success-subtle); }
.failed .result-heading strong { color: var(--kms-danger-strong); background: var(--kms-danger-subtle); }
.incomplete .result-heading strong, .running .result-heading strong { color: var(--kms-warning-strong); background: var(--kms-warning-subtle); }
.evaluated .result-heading strong { color: var(--kms-success-strong); background: var(--kms-success-subtle); }
time { font-size: 11px; color: var(--kms-text-tertiary); font-variant-numeric: tabular-nums; }
p { margin: 8px 0; overflow-wrap: anywhere; color: var(--kms-text-secondary); }
.codes { margin: 12px 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; padding: 12px 0; border-top: 1px solid var(--kms-border); border-bottom: 1px solid var(--kms-border); }
.codes div { min-width: 0; }
dt { font-size: 11px; color: var(--kms-text-tertiary); }
dd { margin: 4px 0 0; font-size: 11px; font-weight: 550; overflow-wrap: anywhere; color: var(--kms-text-primary); }
.rule-evidence { margin: 12px 0; display: grid; gap: 8px; }
.rule-evidence > div { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; }
.rule-evidence dd { margin: 0; font-size: 12px; font-weight: 400; }
.rule-evidence dd code { display: inline; margin: 0 4px; }
ol { list-style: none; counter-reset: trace; padding: 0; margin: 12px 0 0; }
li { counter-increment: trace; position: relative; margin: 0; padding: 0 0 18px 28px; }
li::before { content: counter(trace); position: absolute; left: 0; top: 1px; width: 18px; height: 18px; border: 1px solid var(--kms-border); border-radius: 50%; display: grid; place-items: center; font-size: 10px; color: var(--kms-text-tertiary); }
li:not(:last-child)::after { content: ''; position: absolute; width: 1px; left: 9px; top: 24px; bottom: 5px; background: var(--kms-border); }
li strong { font-size: 12px; color: var(--kms-text-primary); font-weight: 550; }
li code { display: block; overflow-wrap: anywhere; font-family: var(--kms-font-mono); font-size: 11px; color: var(--kms-text-secondary); margin: 4px 0; }
li > span, .trace-heading span { font-size: 11px; color: var(--kms-text-tertiary); overflow-wrap: anywhere; }
.trace-heading span { font-variant-numeric: tabular-nums; }
@media (max-width: 600px) { .codes { grid-template-columns: 1fr; gap: 10px; } .codes div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; } dd { margin-top: 0; } }
@media (max-width: 600px) { .control-check { grid-template-columns: 1fr; gap: 4px; } }
</style>
