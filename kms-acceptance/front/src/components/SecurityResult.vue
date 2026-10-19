<template>
  <section class="security-result" :class="outcome.state" :data-case-id="run.caseId">
    <div class="result-heading"><strong>{{ outcome.label }}</strong><time :title="run.finishedAt || run.startedAt">{{ formatTime(run.finishedAt || run.startedAt) }}</time></div>
    <p v-if="legacyEvidence">此记录只有旧版判定证据，请重新执行；不计入本次通过数量。</p>
    <p v-else>{{ run.error || run.summary || run.stage || '尚未获得完整判定证据。' }}</p>
    <dl v-if="run.testInput || run.validationRule" class="rule-evidence">
      <div><dt>本次测试输入</dt><dd>{{ run.testInput }}</dd></div>
      <div><dt>对应校验规则</dt><dd>{{ run.validationRule }}</dd></div>
      <div><dt>预期拒绝原因</dt><dd>{{ run.expectedReason || '未记录' }}</dd></div>
      <div><dt>实际拒绝原因</dt><dd>{{ run.actualReason || '未获得可核验原因' }}</dd></div>
      <div><dt>原因匹配</dt><dd>{{ run.reasonMatched === true ? '匹配' : '未匹配，不计为通过' }}</dd></div>
    </dl>
    <dl v-if="run.expectedCode || run.actualCode" class="codes">
      <div><dt>预期拒绝码</dt><dd>{{ run.expectedCode || '未记录' }}</dd></div>
      <div><dt>实际拒绝码</dt><dd>{{ run.actualCode || '未取得' }}</dd></div>
      <div><dt>正常请求验证</dt><dd>{{ run.legalControlPassed === true ? '通过' : '未取得完整证据' }}</dd></div>
    </dl>
    <p v-if="outcome.state === 'running' && run.stage" class="live-stage" role="status">当前步骤：{{ run.stage }}</p>
    <details v-if="run.requests?.length || run.summary" class="evidence-details" open>
      <summary>测试过程与判定证据（{{ run.requests?.length || 0 }} 条请求）</summary>
      <ol><li v-for="(trace, index) in run.requests || []" :key="index"><div class="trace-heading"><strong>{{ trace.name || `请求 ${index + 1}` }}</strong><span v-if="trace.recordedAt" :title="trace.recordedAt">{{ formatTime(trace.recordedAt) }} · 耗时 {{ trace.durationMs }} ms</span></div><code>{{ trace.method }} {{ trace.url }}</code><span>HTTP {{ trace.statusCode || '未取得响应' }} · {{ trace.message }}</span></li></ol>
      <p v-for="note in notes" :key="note">{{ note }}</p>
    </details>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { securityOutcome } from '../utils/test-results'
const props = defineProps({ run: { type: Object, required: true } })
const outcome = computed(() => securityOutcome(props.run))
const notes = computed(() => (props.run.notes || []).filter(note => !note.startsWith('固定协议探针；')))
const legacyEvidence = computed(() => props.run.status === 'completed' && props.run.passed === true && props.run.evidenceVersion !== 2)
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour12: false }) }
</script>

<style scoped>
.security-result { padding-top: 12px; font-size: 12px; line-height: 1.7; min-width: 0; }
.result-heading, .trace-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.result-heading strong { padding: 2px 8px; border-radius: 5px; font-size: 11px; font-weight: 600; color: var(--kms-text-secondary); background: var(--kms-surface-3); }
.passed .result-heading strong { color: var(--kms-success-strong); background: var(--kms-success-subtle); }
.failed .result-heading strong { color: var(--kms-danger-strong); background: var(--kms-danger-subtle); }
.incomplete .result-heading strong, .running .result-heading strong { color: var(--kms-warning-strong); background: var(--kms-warning-subtle); }
time { font-size: 11px; color: var(--kms-text-tertiary); font-variant-numeric: tabular-nums; }
p { margin: 8px 0; overflow-wrap: anywhere; color: var(--kms-text-secondary); }
.codes { margin: 12px 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; padding: 12px 0; border-top: 1px solid var(--kms-border); border-bottom: 1px solid var(--kms-border); }
.codes div { min-width: 0; }
dt { font-size: 11px; color: var(--kms-text-tertiary); }
dd { margin: 4px 0 0; font-size: 11px; font-weight: 550; overflow-wrap: anywhere; color: var(--kms-text-primary); }
.rule-evidence { margin: 12px 0; display: grid; gap: 8px; }
.rule-evidence > div { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; }
.rule-evidence dd { margin: 0; font-size: 12px; font-weight: 400; }
.evidence-details { margin-top: 10px; color: var(--kms-text-secondary); }
summary { cursor: pointer; color: var(--kms-brand-text); font-weight: 550; font-size: 12px; }
summary:focus-visible { outline: 2px solid var(--kms-brand); outline-offset: 3px; }
ol { list-style: none; counter-reset: trace; padding: 0; margin: 12px 0 0; }
li { counter-increment: trace; position: relative; margin: 0; padding: 0 0 18px 28px; }
li::before { content: counter(trace); position: absolute; left: 0; top: 1px; width: 18px; height: 18px; border: 1px solid var(--kms-border); border-radius: 50%; display: grid; place-items: center; font-size: 10px; color: var(--kms-text-tertiary); }
li:not(:last-child)::after { content: ''; position: absolute; width: 1px; left: 9px; top: 24px; bottom: 5px; background: var(--kms-border); }
li strong { font-size: 12px; color: var(--kms-text-primary); font-weight: 550; }
li code { display: block; overflow-wrap: anywhere; font-family: var(--kms-font-mono); font-size: 11px; color: var(--kms-text-secondary); margin: 4px 0; }
li > span, .trace-heading span { font-size: 11px; color: var(--kms-text-tertiary); overflow-wrap: anywhere; }
.trace-heading span { font-variant-numeric: tabular-nums; }
@media (max-width: 600px) { .codes { grid-template-columns: 1fr; gap: 10px; } .codes div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; } dd { margin-top: 0; } }
</style>
