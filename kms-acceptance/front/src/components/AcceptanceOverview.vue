<template>
  <section class="acceptance-overview">
    <div class="overview-head">
      <div>
        <h2>验收流程</h2>
      </div>
      <div class="scope-chip">
        <span>验收账号</span>
        <code>{{ health?.acceptanceUser || 'acceptance_user' }}</code>
      </div>
    </div>

    <div class="pipeline">
      <article v-for="(step, index) in steps" :key="step.id" class="pipeline-step" :class="step.state">
        <div class="step-index">0{{ index + 1 }}</div>
        <div class="step-body">
          <div class="step-topline">
            <h3>{{ step.title }}</h3>
            <span class="step-state">{{ step.stateText }}</span>
          </div>
          <div class="step-meta">
            <span>{{ step.scenario?.name || '未加载场景' }}</span>
            <strong>{{ step.measurement }}</strong>
          </div>
        </div>
      </article>
    </div>

    <div class="overview-foot">
      <span class="foot-label">推荐顺序</span>
      <span>生成准备</span><i>→</i><span>更新吞吐</span><i>→</i><span>回收吞吐</span><i>→</i><span>回收率核验</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { health, scenarios, runs } from '../store'
import { performanceOutcome, measuredPerformance } from '../utils/test-results'

const scenarioMap = computed(() => new Map(scenarios.value.map((item) => [item.id, item])))
const steps = computed(() => {
  const config = [
    { id: 'generate-tps', title: '生成 TPS' },
    { id: 'update-tps', title: '更新 TPS' },
    { id: 'revoke-tps', title: '回收 TPS' },
    { id: 'revoke-rate', title: '最终回收率' }
  ]
  return config.map((item) => {
    const scenario = scenarioMap.value.get(item.id)
    const last = [...runs.value].find((run) => run.scenarioId === item.id)
    const outcome = performanceOutcome(last)
    const value = measuredPerformance(last)
    const unit = item.id === 'revoke-rate' ? '%' : 'TPS'
    return { ...item, scenario, state: outcome.state === 'passed' ? 'passed' : last ? 'attention' : 'idle', stateText: outcome.label, measurement: value === null ? '尚无有效测量' : `实测 ${formatTps(value)} ${unit}` }
  })
})

function formatTps(value) {
  const n = Number(value || 0)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.acceptance-overview { margin-bottom: 28px; }
.overview-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 18px; }
.overview-head h2 { margin: 0; color: var(--kms-text-primary); font-size: 21px; letter-spacing: -.02em; }
.scope-chip { display: flex; flex-direction: column; gap: 5px; min-width: 170px; padding: 12px 14px; border: 1px solid var(--kms-border); border-radius: var(--kms-radius); background: var(--kms-surface-1); }
.scope-chip span { color: var(--kms-text-tertiary); font-size: 11px; }
.scope-chip code { color: var(--kms-text-primary); font-family: var(--kms-font-mono); font-size: 12px; }
.pipeline { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.pipeline-step { display: flex; gap: 12px; min-height: 128px; padding: 16px; border: 1px solid var(--kms-border); border-radius: var(--kms-radius); background: var(--kms-surface-1); }
.pipeline-step.passed { border-color: var(--kms-success-border); background: var(--kms-success-subtle); }
.pipeline-step.attention { border-color: var(--kms-warning-border); background: var(--kms-warning-subtle); }
.step-index { color: var(--kms-brand-text); font-family: var(--kms-font-mono); font-size: 12px; font-weight: 700; }
.step-body { min-width: 0; flex: 1; }
.step-topline { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.step-topline h3 { margin: 0; color: var(--kms-text-primary); font-size: 15px; }
.step-state { color: var(--kms-text-tertiary); font-size: 11px; white-space: nowrap; }
.passed .step-state { color: var(--kms-success-strong); }
.attention .step-state { color: var(--kms-warning-strong); }
.step-meta { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; margin-top: 10px; color: var(--kms-text-tertiary); font-size: 11px; }
.step-meta strong { color: var(--kms-text-secondary); font-weight: 600; }
.overview-foot { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin-top: 12px; color: var(--kms-text-tertiary); font-size: 12px; }
.foot-label { color: var(--kms-text-secondary); font-weight: 600; }
.overview-foot i { color: var(--kms-brand-text); font-style: normal; }
@media (max-width: 1200px) { .pipeline { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) { .overview-head { flex-direction: column; } .pipeline { grid-template-columns: 1fr; } .foot-note { margin-left: 0; width: 100%; } }
</style>
