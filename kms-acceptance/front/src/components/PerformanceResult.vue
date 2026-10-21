<template>
  <section class="performance-result" :class="outcome.state">
    <div class="result-heading"><strong>{{ outcome.label }}</strong><time :title="run.finishedAt || run.startedAt">{{ formatTime(run.finishedAt || run.startedAt) }}</time></div>
    <dl>
      <div><dt>实测{{ unit === '%' ? '异常密钥回收率' : fixedUpdate ? '密钥实际更新速率' : (abnormal ? '异常自动回收速率' : '成功请求速率') }}</dt><dd>{{ value === null ? '尚无有效测量' : `${number(value)} ${unit}` }}</dd></div>
      <div><dt>验收要求</dt><dd>{{ operator }} {{ number(target) }} {{ unit }}</dd></div>
    </dl>
    <p v-if="run.error" class="result-error">{{ run.error }}</p>
    <p v-else-if="run.stage">{{ run.stage }}</p>
    <p>测试时间：{{ formatTime(run.startedAt) || '未开始' }} → {{ formatTime(run.finishedAt) || '进行中' }}</p>
    <details class="evidence-details" open>
      <summary>测试过程与测量证据</summary>
      <ol v-if="run.stages?.length"><li v-for="(step, index) in run.stages" :key="index">{{ formatTime(step.at) }} · {{ step.label }}</li></ol>
      <p v-else>未记录阶段过程</p>
      <template v-if="abnormal">
        <p>先写入异常密钥记录，再由系统检测并自动回收。正常密钥和仅需人工复核的告警作为对照。</p>
        <p v-if="unit === '%'">回收率 = 最终回收成功数 ÷ 实际发起回收密钥数 × 100%；发起后失败的计入分母，未发起的单独展示。与速率要求独立，不按固定秒数截断。</p>
        <dl>
          <div><dt>异常样本 / 检测 / 实际回收</dt><dd>{{ number(abnormal.injected) }} / {{ number(abnormal.detected) }} / {{ number(abnormal.revoked) }}</dd></div>
          <div><dt>实际发起 / 成功 / 失败</dt><dd>{{ number(abnormal.attempted) }} / {{ number(abnormal.revoked) }} / {{ number(abnormal.attempted - abnormal.revoked) }}</dd></div>
          <div><dt>未发起回收</dt><dd>{{ number(abnormal.injected - abnormal.attempted) }}</dd></div>
          <div><dt>对照通过</dt><dd>{{ number(abnormal.controlsPassed) }} / {{ number(abnormal.controls) }}</dd></div>
          <div><dt>池项 / 会话失效</dt><dd>{{ number(abnormal.poolRevoked) }} / {{ number(abnormal.sessionsRevoked) }}</dd></div>
          <div><dt>扫描回收 / 全流程耗时</dt><dd>{{ number(abnormal.elapsedMs) }} / {{ number(abnormal.totalMs) }} ms</dd></div>
        </dl>
        <table><caption>异常检测与回收明细</caption><thead><tr><th>异常类型</th><th>样本数</th><th>已检测</th><th>已回收</th></tr></thead>
          <tbody><tr v-for="rule in abnormal.rules" :key="rule.rule"><td>{{ ruleText(rule.rule) }}</td><td>{{ number(rule.injected) }}</td><td>{{ number(rule.detected) }}</td><td>{{ number(rule.revoked) }}</td></tr></tbody></table>
        <table><caption>跨批次回收记录（每批上限 {{ number(abnormal.batchLimit) }} 条）</caption><thead><tr><th>批次</th><th>发起</th><th>成功</th><th>耗时 ms</th></tr></thead>
          <tbody><tr v-for="(batch, index) in abnormal.batches" :key="index"><td>{{ index + 1 }}</td><td>{{ number(batch.attempted) }}</td><td>{{ number(batch.revoked) }}</td><td>{{ number(batch.elapsedMs) }}</td></tr></tbody></table>
        <p>{{ abnormal.cleanupComplete ? '隔离样本已清理，检测和状态快照已归档。' : '样本清理尚未确认。' }} <router-link to="/lifecycle">查看逐钥快照</router-link></p>
      </template>
      <template v-else-if="fixedUpdate">
        <div class="fixed-update-evidence">
          <p>复用已生成的 6000 把 SM2 验收密钥，每把更新一次；版本递增且材料改变才计为完成。</p>
          <dl>
            <div><dt>选取 / 提交 / 受理</dt><dd>{{ number(fixedUpdate.selected) }} / {{ number(fixedUpdate.submitted) }} / {{ number(fixedUpdate.accepted) }}</dd></div>
            <div><dt>版本更新完成</dt><dd>{{ fixedUpdate.verified ? number(fixedUpdate.completed) : '尚未核定' }}</dd></div>
            <div><dt>重复响应 / 请求失败</dt><dd>{{ number(fixedUpdate.duplicates) }} / {{ number(fixedUpdate.rejected) }}</dd></div>
            <div><dt>请求受理速率</dt><dd>{{ number(fixedUpdate.acceptedTps) }} TPS</dd></div>
            <div><dt>提交耗时 / 更新核验耗时</dt><dd>{{ number(fixedUpdate.submissionMs) }} / {{ number(fixedUpdate.elapsedMs) }} ms</dd></div>
          </dl>
          <p>实际更新速率 = 数据库更新完成数 ÷ 从首次提交到落库核验的耗时；包含排队及状态查询，不含密钥池准备、更新前快照与异步上链等待。</p>
          <p v-if="fixedUpdate.sourceRunId">来源生成批次：{{ fixedUpdate.sourceRunId }}</p>
          <router-link to="/lifecycle">查看 6000 把密钥的版本前后状态</router-link>
        </div>
      </template>
      <dl v-else>
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
const abnormal = computed(() => props.run.abnormalEvidence)
const fixedUpdate = computed(() => props.run.fixedUpdateEvidence)
const ruleText = rule => ({ PUBLIC_KEY_MISSING: '公钥缺失', PUBLIC_KEY_HASH_MISSING: '公钥摘要缺失', PUBLIC_KEY_HASH_MISMATCH: '公钥与摘要不匹配' })[rule] || rule
const unit = computed(() => props.criterion?.unit || (props.run.scenarioId === 'revoke-rate' ? '%' : 'TPS'))
const target = computed(() => props.criterion?.target ?? (unit.value === '%' ? props.run.metricCheck?.target : props.run.targetTps))
const operator = computed(() => props.criterion?.operator || (unit.value === '%' ? props.run.metricCheck?.operator || props.scenario?.metricOperator : props.scenario?.targetOperator) || (props.run.scenarioId === 'generate-tps' ? '>' : '>='))
function number(value) { return value === null || value === undefined ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function formatTime(value) { if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour12: false }) }
</script>

<style scoped>
.performance-result { margin-top: 12px; padding-top: 16px; border-top: 1px solid var(--kms-border); font-size: 12px; line-height: 1.7; min-width: 0; }
table { width: 100%; border-collapse: collapse; font-size: inherit; } caption { text-align: left; color: var(--kms-text-secondary); margin-bottom: 8px; } th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--kms-border); } th { color: var(--kms-text-secondary); }
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
