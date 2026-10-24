<template>
  <div class="quantum-evidence">
    <section class="model-process" aria-label="本项攻击模型与计算流程">
      <h4>{{ model?.title || evidence.name }}</h4>
      <p>{{ model?.objective || evidence.scope }}</p>
      <p class="model-input">本次输入：Kyber-512 / 768 / 1024 公开 LWE 参数 · q={{ evidence.estimates[0]?.q }} · <code>{{ model?.method || evidence.model }}</code></p>
    </section>
    <div class="cost-scroll" tabindex="0" role="region" aria-label="Kyber 参数攻击成本">
      <table>
        <caption>本次模型计算结果</caption>
        <thead><tr><th>参数集</th><th>BKZ 块大小 β</th><th>模型参数与分项成本</th><th>总估算运算量</th></tr></thead>
        <tbody><tr v-for="row in costRows" :key="row.variant">
          <th>KYBER-{{ row.variant }}</th><td>{{ row.beta }}</td>
          <td class="model-costs"><span v-for="field in row.fields" :key="field.key">{{ field.name }}：<code>{{ field.value }}</code></span><span v-if="!row.fields.length">未记录分项参数</span></td>
          <td>2<sup>{{ row.log2Rop.toFixed(2) }}</sup> rop</td>
        </tr></tbody>
      </table>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { quantumModels, costFieldNames } from '../config/quantumModels.js'
import { parseCostFields } from '../utils/evidence-presentation.js'
const props = defineProps({ evidence: { type: Object, required: true } })
const model = computed(() => quantumModels[props.evidence.model])
const costRows = computed(() => props.evidence.estimates.map(row => {
  const values = parseCostFields(row.rawCost)
  return { ...row, fields: (model.value?.fields || []).filter(key => values[key] !== undefined).map(key => ({ key, name: costFieldNames[key], value: values[key] })) }
}))
</script>

<style scoped>
.quantum-evidence { margin: 12px 0; font-size: 12px; color: var(--kms-text-secondary); }
p { margin: 8px 0; overflow-wrap: anywhere; line-height: 1.7; }
.cost-scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; min-width: 530px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 9px 12px 9px 0; border-bottom: 1px solid var(--kms-border); white-space: nowrap; }
th { color: var(--kms-text-primary); font-weight: 550; }
.model-process h4 { font-size: 13px; color: var(--kms-text-primary); font-weight: 600; margin: 14px 0 8px; }
.model-process > p { max-width: 72ch; }
.model-process ol { list-style: none; margin: 16px 0; padding: 0; display: grid; gap: 12px; }
.model-process li { display: flex; align-items: flex-start; gap: 10px; }
.model-process li p { margin: 2px 0 0; max-width: 70ch; }
.model-process strong { color: var(--kms-text-primary); font-weight: 550; }
.step-number { flex: 0 0 20px; line-height: 20px; text-align: center; font-variant-numeric: tabular-nums; border: 1px solid var(--kms-border); border-radius: 50%; }
caption { text-align: left; font-weight: 550; color: var(--kms-text-primary); padding: 10px 0; }
.model-costs span { display: block; font-size: 11px; }
.cost-scroll:focus-visible { outline: 2px solid var(--kms-brand); outline-offset: 3px; }
</style>
